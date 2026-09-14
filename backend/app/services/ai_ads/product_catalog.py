"""Persist Shopify product photos once, then refresh only when the catalog changes.

Storage model: the database row holds the durable copy of every photo (`image_bytes`) and the
local file is only a cache. App instances do not share a filesystem, so a row that points at
`local_path` alone renders as a dead image on any other machine. Reads therefore fall back
cache -> database -> re-download from Shopify, repairing the row on the way.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt_value
from app.db.models import ShopifyCatalogImage, ShopifyCatalogProduct, Store, StoreAIAdsSettings
from app.db.session import SessionLocal
from app.integrations.shopify.client import ShopifyClient
from app.services.ai_ads.asset_store import CreativeAssetStore
from app.services.ai_ads.media_io import (
    archive_image_bytes,
    bytes_to_data_url,
    fetch_image_bytes,
    normalize_image_url,
)
from app.services.ai_ads.product_context import normalize_product
from app.services.ai_ads.schemas import ProductContext, ProductImage

logger = logging.getLogger(__name__)

MAX_STORED_IMAGES = 8
IDENTITY_LIMIT = 4
MANUAL_SOURCE = "manual://upload"

_thread_lock = threading.Lock()
_running_stores: set[str] = set()


def numeric_shopify_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("gid://"):
        text = text.rsplit("/", 1)[-1]
    return text


def is_refetchable(source_url: str | None) -> bool:
    """True when the photo can be pulled from Shopify again if the bytes are lost."""
    return str(source_url or "").strip().lower().startswith("http")


def product_image_payloads(product: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for img in product.get("images") or []:
        if not isinstance(img, dict):
            continue
        src = str(img.get("src") or img.get("url") or "").strip()
        if not src:
            continue
        out.append(img)
    if not out and isinstance(product.get("image"), dict):
        src = str(product["image"].get("src") or product["image"].get("url") or "").strip()
        if src:
            out.append(product["image"])
    return out


def image_key(img: dict[str, Any]) -> str:
    sid = numeric_shopify_id(img.get("id"))
    if sid:
        return sid
    src = normalize_image_url(str(img.get("src") or img.get("url") or ""))
    return hashlib.sha1(src.split("?")[0].encode("utf-8")).hexdigest()[:16]


def image_fingerprint(images: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for img in images:
        sid = numeric_shopify_id(img.get("id"))
        src = normalize_image_url(str(img.get("src") or img.get("url") or ""))
        updated = str(img.get("updated_at") or "")
        parts.append(f"{sid}|{src}|{updated}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def images_needing_download(
    wanted: list[tuple[str, str]],
    cached: dict[str, tuple[str, bool]],
) -> list[str]:
    """Return image keys that are new, retouched, or whose bytes are gone."""
    need: list[str] = []
    for key, src in wanted:
        prev = cached.get(key)
        if not prev or prev[0] != src or not prev[1]:
            need.append(key)
    return need


class ShopifyProductCatalog:
    def __init__(self, db: Session, store: Store, assets: CreativeAssetStore) -> None:
        self.db = db
        self.store = store
        self.assets = assets

    def get_product_row(self, product_id: str) -> ShopifyCatalogProduct | None:
        pid = numeric_shopify_id(product_id)
        return self.db.scalar(
            select(ShopifyCatalogProduct).where(
                ShopifyCatalogProduct.store_id == self.store.id,
                ShopifyCatalogProduct.shopify_product_id == pid,
            )
        )

    def listed_images(self, product_id: str) -> list[ShopifyCatalogImage]:
        pid = numeric_shopify_id(product_id)
        return list(
            self.db.scalars(
                select(ShopifyCatalogImage)
                .where(
                    ShopifyCatalogImage.store_id == self.store.id,
                    ShopifyCatalogImage.shopify_product_id == pid,
                )
                .order_by(ShopifyCatalogImage.position.asc())
            ).all()
        )

    def store_images(self) -> list[ShopifyCatalogImage]:
        return list(
            self.db.scalars(
                select(ShopifyCatalogImage)
                .where(ShopifyCatalogImage.store_id == self.store.id)
                .order_by(ShopifyCatalogImage.position.asc())
            ).all()
        )

    # ---------------------------------------------------------------- photo bytes

    def _durable_row_ids(self, rows: list[ShopifyCatalogImage]) -> set[str]:
        """Ids of rows holding durable bytes. One cheap query; never transfers the blobs."""
        ids = [row.id for row in rows if getattr(row, "id", None)]
        if not ids:
            return set()
        found = self.db.scalars(
            select(ShopifyCatalogImage.id).where(
                ShopifyCatalogImage.id.in_(ids),
                ShopifyCatalogImage.image_bytes.isnot(None),
            )
        ).all()
        return set(found)

    def _store_photo_bytes(self, row: ShopifyCatalogImage, data: bytes, mime: str) -> None:
        """Write one photo to both the durable store and the local cache."""
        digest = hashlib.sha256(data).hexdigest()
        saved = self.assets.save_bytes(
            data,
            mime_type=mime,
            prefix=f"sku_{row.shopify_product_id}",
            known_hash=digest,
        )
        previous = row.local_path
        row.local_path = saved["relative_path"]
        row.image_bytes = data
        row.mime_type = mime
        row.content_hash = digest
        row.byte_size = len(data)
        row.last_fetched_at = datetime.now(UTC)
        if previous and previous != saved["relative_path"]:
            self.assets.delete_local(previous)

    def photo_bytes(self, row: ShopifyCatalogImage) -> tuple[bytes, str] | None:
        """Bytes from the local cache, else the durable copy (which re-warms the cache)."""
        cached = self.assets.read_bytes(row.local_path)
        if cached:
            return cached
        blob = row.image_bytes
        if not blob:
            return None
        mime = row.mime_type or "image/jpeg"
        try:
            saved = self.assets.save_bytes(
                blob,
                mime_type=mime,
                prefix=f"sku_{row.shopify_product_id}",
                known_hash=row.content_hash or None,
            )
            row.local_path = saved["relative_path"]
        except Exception as err:
            logger.info("ai_ads catalog cache warm failed key=%s err=%s", row.image_key, err)
        return blob, mime

    async def materialize_photo(
        self,
        row: ShopifyCatalogImage,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> tuple[bytes, str] | None:
        """Bytes for one photo, re-downloading from Shopify when the stored copy is gone."""
        previous_path = row.local_path
        got = self.photo_bytes(row)
        if got:
            if row.local_path != previous_path:
                self.db.commit()
            return got
        if not is_refetchable(row.source_url):
            return None
        fetched = await fetch_image_bytes(
            row.source_url,
            referer=f"https://{self.store.shop_domain}/",
            shop_domain=self.store.shop_domain,
            client=client,
        )
        if not fetched:
            logger.warning(
                "ai_ads catalog photo unrecoverable store_id=%s product=%s key=%s",
                self.store.id,
                row.shopify_product_id,
                row.image_key,
            )
            return None
        try:
            archived = archive_image_bytes(fetched[0])
        except Exception as err:
            logger.info("ai_ads catalog archive failed key=%s err=%s", row.image_key, err)
            return None
        self._store_photo_bytes(row, archived[0], archived[1])
        self.db.commit()
        logger.info(
            "ai_ads catalog photo repaired store_id=%s product=%s key=%s",
            self.store.id,
            row.shopify_product_id,
            row.image_key,
        )
        return archived

    async def photo_for_key(self, product_id: str, key: str) -> tuple[bytes, str] | None:
        pid = numeric_shopify_id(product_id)
        row = self.db.scalar(
            select(ShopifyCatalogImage).where(
                ShopifyCatalogImage.store_id == self.store.id,
                ShopifyCatalogImage.shopify_product_id == pid,
                ShopifyCatalogImage.image_key == str(key),
            )
        )
        if not row:
            return None
        return await self.materialize_photo(row)

    def photo_url(self, row: ShopifyCatalogImage) -> str:
        """Served through the API so a cold cache repairs itself instead of returning 404."""
        base = (
            f"{settings.api_prefix}/ai-ads/stores/{self.store.id}"
            f"/products/{row.shopify_product_id}/photos/{row.image_key}"
        )
        version = (row.content_hash or "")[:12]
        return f"{base}?v={version}" if version else base

    # ---------------------------------------------------------------- product context

    def upsert_product_row(self, raw: dict[str, Any]) -> ShopifyCatalogProduct:
        ctx = normalize_product(
            raw,
            shop_domain=self.store.shop_domain,
            currency=self.store.currency,
            brand_name=self.store.name,
        )
        payloads = product_image_payloads(raw)[:MAX_STORED_IMAGES]
        fingerprint = image_fingerprint(payloads)
        pid = numeric_shopify_id(ctx.product_id or raw.get("id"))
        row = self.get_product_row(pid)
        if not row:
            row = ShopifyCatalogProduct(store_id=self.store.id, shopify_product_id=pid)
            self.db.add(row)
        row.title = ctx.title
        row.handle = str(raw.get("handle") or "")
        row.description = ctx.description or ""
        row.product_url = ctx.product_url
        row.price = ctx.price
        row.currency = ctx.currency
        row.images_json = json.dumps(
            [
                {
                    "id": numeric_shopify_id(img.get("id")) or None,
                    "src": str(img.get("src") or img.get("url") or ""),
                    "alt": img.get("alt"),
                    "width": img.get("width"),
                    "height": img.get("height"),
                    "position": img.get("position") if img.get("position") is not None else index,
                    "updated_at": img.get("updated_at"),
                    "key": image_key(img),
                }
                for index, img in enumerate(payloads)
            ]
        )
        if row.image_fingerprint != fingerprint:
            row.appearance_lock_fingerprint = ""
        row.image_fingerprint = fingerprint
        row.last_synced_at = datetime.now(UTC)
        self.db.flush()
        return row

    def load_context(self, product_id: str) -> ProductContext | None:
        row = self.get_product_row(product_id)
        if not row:
            return None
        images: list[ProductImage] = []
        try:
            payload = json.loads(row.images_json or "[]")
        except json.JSONDecodeError:
            payload = []
        for img in payload:
            if not isinstance(img, dict):
                continue
            src = str(img.get("src") or "").strip()
            if not src:
                continue
            images.append(
                ProductImage(
                    src=src,
                    alt=str(img.get("alt") or row.title) or None,
                    width=img.get("width") if isinstance(img.get("width"), int) else None,
                    height=img.get("height") if isinstance(img.get("height"), int) else None,
                    shopify_id=str(img.get("id") or "") or None,
                    position=img.get("position") if isinstance(img.get("position"), int) else None,
                    updated_at=str(img.get("updated_at") or "") or None,
                )
            )
        ctx = ProductContext(
            product_id=row.shopify_product_id,
            title=row.title or "Untitled product",
            description=row.description or "",
            price=row.price,
            currency=row.currency,
            product_url=row.product_url,
            images=images,
        )
        if row.appearance_lock and row.appearance_lock_fingerprint == row.image_fingerprint:
            ctx.brand_context = {"appearance_lock": row.appearance_lock}
        return ctx

    def cached_identity_bytes(self, product_id: str, *, limit: int = IDENTITY_LIMIT) -> list[tuple[bytes, str]]:
        out: list[tuple[bytes, str]] = []
        for row in self.listed_images(product_id):
            got = self.photo_bytes(row)
            if not got:
                continue
            out.append(got)
            if len(out) >= limit:
                break
        return out

    def attach_identity(self, product: ProductContext, refs: list[tuple[bytes, str]]) -> ProductContext:
        data_urls = [bytes_to_data_url(raw, mime) for raw, mime in refs[:3] if raw]
        product.brand_context = dict(product.brand_context or {})
        if data_urls:
            product.brand_context["identity_data_urls"] = data_urls
        return product

    def appearance_lock_if_current(self, product_id: str, fingerprint: str) -> str | None:
        row = self.get_product_row(product_id)
        if (
            row
            and row.appearance_lock
            and row.appearance_lock_fingerprint
            and row.appearance_lock_fingerprint == fingerprint
        ):
            return row.appearance_lock
        return None

    def save_appearance_lock(self, product_id: str, fingerprint: str, text: str) -> None:
        row = self.get_product_row(product_id)
        if not row:
            return
        row.appearance_lock = text or ""
        row.appearance_lock_fingerprint = fingerprint
        self.db.commit()

    def cached_ready(self, product_id: str, fingerprint: str) -> bool:
        row = self.get_product_row(product_id)
        if not row or row.image_fingerprint != fingerprint:
            return False
        return bool(self.cached_identity_bytes(product_id, limit=1))

    def has_usable_photos(self, product_id: str) -> bool:
        """True when photos exist or can be rebuilt without operator help."""
        rows = self.listed_images(product_id)
        if not rows:
            return False
        durable = self._durable_row_ids(rows)
        return any(
            row.id in durable or self.assets.exists(row.local_path) or is_refetchable(row.source_url)
            for row in rows
        )

    # ---------------------------------------------------------------- maintenance

    def backfill_durable_bytes(self, *, limit: int = 40) -> int:
        """Copy cached files into the durable store for rows written before it existed."""
        rows = self.store_images()
        if not rows:
            return 0
        durable = self._durable_row_ids(rows)
        filled = 0
        for row in rows:
            if filled >= limit:
                break
            if row.id in durable:
                continue
            got = self.assets.read_bytes(row.local_path)
            if not got:
                continue
            row.image_bytes = got[0]
            row.mime_type = got[1] or row.mime_type
            row.byte_size = len(got[0])
            if not row.content_hash:
                row.content_hash = hashlib.sha256(got[0]).hexdigest()
            filled += 1
        if filled:
            self.db.commit()
            logger.info("ai_ads catalog backfilled %s photos store_id=%s", filled, self.store.id)
        return filled

    def prune_unrecoverable_photos(self) -> int:
        """Drop rows with no bytes anywhere and no Shopify source. They only render as broken."""
        rows = self.store_images()
        if not rows:
            return 0
        durable = self._durable_row_ids(rows)
        dropped = 0
        for row in rows:
            if row.id in durable or is_refetchable(row.source_url):
                continue
            if self.assets.exists(row.local_path):
                continue
            self.db.delete(row)
            dropped += 1
        if dropped:
            self.db.commit()
            logger.warning(
                "ai_ads catalog pruned %s unrecoverable photos store_id=%s", dropped, self.store.id
            )
        return dropped

    def adopt_orphan_disk_photos(self) -> int:
        """Register sku_*.jpg files that were written to disk but never committed."""
        folder = self.assets.dir
        if not folder.is_dir():
            return 0
        existing = self.store_images()
        seen_paths = {(img.local_path or "").replace("\\", "/") for img in existing}
        seen_keys = {(img.shopify_product_id, img.image_key) for img in existing}
        counts: dict[str, int] = {}
        for img in existing:
            counts[img.shopify_product_id] = max(counts.get(img.shopify_product_id, 0), img.position + 1)
        added = 0
        for path in folder.iterdir():
            if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            if not path.name.startswith("sku_"):
                continue
            pid, sep, _rest = path.name[4:].partition("_")
            if not sep or not pid.isdigit():
                continue
            if not self.get_product_row(pid):
                continue
            rel = self.assets.relative(path)
            if rel in seen_paths:
                continue
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            key = f"manual_{digest[:16]}"
            if (pid, key) in seen_keys:
                continue
            mime = (
                "image/jpeg"
                if path.suffix.lower() in {".jpg", ".jpeg"}
                else f"image/{path.suffix.lower().lstrip('.')}"
            )
            position = counts.get(pid, 0)
            self.db.add(
                ShopifyCatalogImage(
                    store_id=self.store.id,
                    shopify_product_id=pid,
                    image_key=key,
                    shopify_image_id=None,
                    source_url=MANUAL_SOURCE,
                    position=position,
                    local_path=rel,
                    image_bytes=data,
                    mime_type=mime,
                    content_hash=digest,
                    byte_size=len(data),
                    last_fetched_at=datetime.now(UTC),
                )
            )
            seen_paths.add(rel)
            seen_keys.add((pid, key))
            counts[pid] = position + 1
            added += 1
        if added:
            self.db.commit()
        return added

    # ---------------------------------------------------------------- picker

    def list_picker_cards(self) -> list[dict[str, Any]]:
        """Saved catalog rows for the Generate picker. No Shopify calls, no file reads."""
        products = list(
            self.db.scalars(
                select(ShopifyCatalogProduct)
                .where(ShopifyCatalogProduct.store_id == self.store.id)
                .order_by(ShopifyCatalogProduct.title.asc())
            ).all()
        )
        stored = self.store_images()
        durable = self._durable_row_ids(stored)
        photos_by_pid: dict[str, list[str]] = {}
        ready_by_pid: dict[str, int] = {}
        for img in stored:
            on_disk = self.assets.exists(img.local_path)
            has_bytes = img.id in durable or on_disk
            if not has_bytes and not is_refetchable(img.source_url):
                continue
            photos_by_pid.setdefault(img.shopify_product_id, []).append(self.photo_url(img))
            if has_bytes:
                ready_by_pid[img.shopify_product_id] = ready_by_pid.get(img.shopify_product_id, 0) + 1
        out: list[dict[str, Any]] = []
        for row in products:
            photos = photos_by_pid.get(row.shopify_product_id) or []
            src = photos[0] if photos else None
            if not src:
                try:
                    payload = json.loads(row.images_json or "[]")
                except json.JSONDecodeError:
                    payload = []
                if payload and isinstance(payload[0], dict):
                    src = str(payload[0].get("src") or "") or None
            out.append(
                {
                    "id": row.shopify_product_id,
                    "title": row.title,
                    "price": row.price,
                    "currency": row.currency,
                    "image": src,
                    "photos": photos,
                    "product_url": row.product_url,
                    "photos_cached": bool(photos),
                    "photos_ready": ready_by_pid.get(row.shopify_product_id, 0),
                }
            )
        return out

    def product_picker_card(self, product_id: str) -> dict[str, Any] | None:
        pid = numeric_shopify_id(product_id)
        for card in self.list_picker_cards():
            if str(card.get("id")) == pid:
                return card
        return None

    # ---------------------------------------------------------------- writes

    def store_manual_photos(self, product_id: str, blobs: list[bytes]) -> dict[str, Any]:
        """Save operator-uploaded stills once. Generate reuses these files after that."""
        pid = numeric_shopify_id(product_id)
        if not pid:
            raise ValueError("product_id is required")
        row = self.get_product_row(pid)
        if not row:
            row = ShopifyCatalogProduct(store_id=self.store.id, shopify_product_id=pid)
            self.db.add(row)
            self.db.flush()
        existing = self.listed_images(pid)
        existing_keys = {img.image_key for img in existing}
        room = MAX_STORED_IMAGES - len(existing)
        if room <= 0:
            card = self.product_picker_card(pid)
            if card:
                return card
            raise ValueError("This product already has the maximum number of saved pictures.")
        added = 0
        duplicates = 0
        rejected = 0
        position = max((img.position for img in existing), default=-1) + 1
        for data in blobs:
            if added >= room:
                break
            if not data or len(data) < 32:
                rejected += 1
                continue
            try:
                archived = archive_image_bytes(data)
            except Exception as err:
                rejected += 1
                logger.info("ai_ads manual photo rejected product=%s err=%s", pid, err)
                continue
            digest = hashlib.sha256(archived[0]).hexdigest()
            key = f"manual_{digest[:16]}"
            if key in existing_keys:
                duplicates += 1
                continue
            image_row = ShopifyCatalogImage(
                store_id=self.store.id,
                shopify_product_id=pid,
                image_key=key,
                shopify_image_id=None,
                source_url=MANUAL_SOURCE,
                alt=row.title or None,
                position=position,
            )
            self.db.add(image_row)
            self._store_photo_bytes(image_row, archived[0], archived[1])
            existing_keys.add(key)
            position += 1
            added += 1
        if added:
            row.last_images_fetched_at = datetime.now(UTC)
            self.db.commit()
        if not added and rejected and not duplicates:
            raise ValueError(
                "Could not use those pictures. The server converts and compresses PNG automatically "
                "— try a different file if this one is damaged."
            )
        card = self.product_picker_card(pid)
        if not card:
            raise ValueError("Could not save product pictures")
        return card

    def clear_product_photos(self, product_id: str) -> dict[str, Any] | None:
        pid = numeric_shopify_id(product_id)
        for img in self.listed_images(pid):
            self.assets.delete_local(img.local_path)
            self.db.delete(img)
        row = self.get_product_row(pid)
        if row:
            row.last_images_fetched_at = None
        self.db.commit()
        return self.product_picker_card(pid)

    async def ensure_product_images(
        self,
        raw: dict[str, Any],
        *,
        limit: int = MAX_STORED_IMAGES,
    ) -> list[tuple[bytes, str]]:
        row = self.upsert_product_row(raw)
        pid = row.shopify_product_id
        payloads = product_image_payloads(raw)[:limit]
        wanted = [
            (image_key(img), normalize_image_url(str(img.get("src") or img.get("url") or "")))
            for img in payloads
        ]
        existing_rows = {img.image_key: img for img in self.listed_images(pid)}
        durable = self._durable_row_ids(list(existing_rows.values()))
        cached_map = {
            key: (img.source_url, img.id in durable or self.assets.exists(img.local_path))
            for key, img in existing_rows.items()
        }
        need = set(images_needing_download(wanted, cached_map))
        referer = f"https://{self.store.shop_domain}/"
        identity: list[tuple[bytes, str]] = []
        wanted_keys = {key for key, _src in wanted}
        stored = 0
        failed = 0

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=8.0), follow_redirects=True
        ) as client:
            for position, img in enumerate(payloads):
                key = image_key(img)
                src = normalize_image_url(str(img.get("src") or img.get("url") or ""))
                cached_row = existing_rows.get(key)
                if key not in need and cached_row:
                    got = self.photo_bytes(cached_row)
                    if got:
                        identity.append(got)
                        continue
                fetched = await fetch_image_bytes(
                    src, referer=referer, shop_domain=self.store.shop_domain, client=client
                )
                if not fetched:
                    failed += 1
                    if cached_row:
                        stale = self.photo_bytes(cached_row)
                        if stale:
                            logger.warning(
                                "ai_ads catalog kept stale photo store_id=%s product=%s key=%s",
                                self.store.id,
                                pid,
                                key,
                            )
                            identity.append(stale)
                    continue
                try:
                    archived = archive_image_bytes(fetched[0])
                except Exception as err:
                    failed += 1
                    logger.info("ai_ads catalog archive skipped key=%s err=%s", key, err)
                    continue
                image_row = cached_row or ShopifyCatalogImage(
                    store_id=self.store.id,
                    shopify_product_id=pid,
                    image_key=key,
                )
                if not cached_row:
                    self.db.add(image_row)
                image_row.shopify_image_id = numeric_shopify_id(img.get("id")) or None
                image_row.source_url = src
                image_row.alt = str(img.get("alt") or "") or None
                image_row.position = int(img.get("position") or position)
                image_row.width = img.get("width") if isinstance(img.get("width"), int) else None
                image_row.height = img.get("height") if isinstance(img.get("height"), int) else None
                self._store_photo_bytes(image_row, archived[0], archived[1])
                identity.append(archived)
                stored += 1

        complete = bool(payloads) and not failed
        if complete:
            for key, old in existing_rows.items():
                if key in wanted_keys or str(key).startswith("manual_"):
                    continue
                self.assets.delete_local(old.local_path)
                self.db.delete(old)
        if not identity:
            identity = self.cached_identity_bytes(pid)

        # Only claim a successful fetch when photos really landed, so a failed run retries.
        if payloads and (stored or not failed):
            row.last_images_fetched_at = datetime.now(UTC)
        elif failed:
            logger.warning(
                "ai_ads catalog photo fetch incomplete store_id=%s product=%s stored=%s failed=%s",
                self.store.id,
                pid,
                stored,
                failed,
            )
        self.db.commit()
        return identity[:IDENTITY_LIMIT]

    def product_photos_complete(self, product_id: str, payloads: list[dict[str, Any]]) -> bool:
        """True when every current Shopify photo already has usable bytes stored."""
        if not payloads:
            return True
        rows = {img.image_key: img for img in self.listed_images(product_id)}
        durable = self._durable_row_ids(list(rows.values()))
        for img in payloads:
            row = rows.get(image_key(img))
            if not row:
                return False
            if row.source_url != normalize_image_url(str(img.get("src") or img.get("url") or "")):
                return False
            if row.id not in durable and not self.assets.exists(row.local_path):
                return False
        return True

    async def sync_store(self, client: ShopifyClient, *, download_images: bool = True) -> list[dict[str, Any]]:
        products = await client.list_products(limit=100, max_items=100)
        for raw in products:
            self.upsert_product_row(raw)
        self.db.commit()
        if not download_images:
            return products
        self.adopt_orphan_disk_photos()
        self.backfill_durable_bytes()
        self.prune_unrecoverable_photos()
        for raw in products:
            pid = numeric_shopify_id(raw.get("id"))
            payloads = product_image_payloads(raw)[:MAX_STORED_IMAGES]
            if self.product_photos_complete(pid, payloads):
                continue
            try:
                await self.ensure_product_images(raw)
            except Exception:
                logger.exception("ai_ads catalog image sync failed store_id=%s product=%s", self.store.id, pid)
        settings_row = self.db.scalar(
            select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == self.store.id)
        )
        if settings_row:
            settings_row.last_product_catalog_at = datetime.now(UTC)
            self.db.commit()
        return products


def enqueue_catalog_sync(store_id: str) -> None:
    """Download missing/changed Shopify photos off the HTTP event loop."""
    with _thread_lock:
        if store_id in _running_stores:
            return
        _running_stores.add(store_id)
    threading.Thread(target=_run_catalog_sync_thread, args=(store_id,), daemon=True).start()


def _run_catalog_sync_thread(store_id: str) -> None:
    asyncio.run(_run_catalog_sync(store_id))


async def _run_catalog_sync(store_id: str) -> None:
    db = SessionLocal()
    try:
        store = db.get(Store, store_id)
        if not store or not store.access_token_encrypted:
            return
        try:
            token = decrypt_value(store.access_token_encrypted)
        except Exception:
            return
        client = ShopifyClient(store.shop_domain, token)
        catalog = ShopifyProductCatalog(db, store, CreativeAssetStore(store.id))
        await catalog.sync_store(client)
        logger.info("ai_ads catalog synced store_id=%s", store_id)
    except Exception:
        logger.exception("ai_ads catalog sync failed store_id=%s", store_id)
    finally:
        db.close()
        with _thread_lock:
            _running_stores.discard(store_id)
