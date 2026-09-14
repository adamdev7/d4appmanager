"""Persist Shopify product photos once, then refresh only when the catalog changes."""

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

_thread_lock = threading.Lock()
_running_stores: set[str] = set()


def numeric_shopify_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("gid://"):
        text = text.rsplit("/", 1)[-1]
    return text


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
    """Return image keys that are new, retouched, or missing on disk."""
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
            got = self.assets.read_bytes(row.local_path)
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

    def list_picker_cards(self) -> list[dict[str, Any]]:
        """Return saved catalog rows for the Generate picker. No Shopify, no disk reads."""
        products = list(
            self.db.scalars(
                select(ShopifyCatalogProduct)
                .where(ShopifyCatalogProduct.store_id == self.store.id)
                .order_by(ShopifyCatalogProduct.title.asc())
            ).all()
        )
        photo_ids = {
            str(pid)
            for pid in self.db.scalars(
                select(ShopifyCatalogImage.shopify_product_id).where(
                    ShopifyCatalogImage.store_id == self.store.id
                )
            ).all()
            if pid
        }
        out: list[dict[str, Any]] = []
        for row in products:
            try:
                payload = json.loads(row.images_json or "[]")
            except json.JSONDecodeError:
                payload = []
            src = None
            if payload and isinstance(payload[0], dict):
                src = str(payload[0].get("src") or "") or None
            out.append(
                {
                    "id": row.shopify_product_id,
                    "title": row.title,
                    "price": row.price,
                    "currency": row.currency,
                    "image": src,
                    "product_url": row.product_url,
                    "photos_cached": row.shopify_product_id in photo_ids,
                }
            )
        return out

    async def ensure_product_images(
        self,
        raw: dict[str, Any],
        *,
        limit: int = MAX_STORED_IMAGES,
    ) -> list[tuple[bytes, str]]:
        row = self.upsert_product_row(raw)
        pid = row.shopify_product_id
        payloads = product_image_payloads(raw)[:limit]
        wanted = [(image_key(img), normalize_image_url(str(img.get("src") or img.get("url") or ""))) for img in payloads]
        existing_rows = {img.image_key: img for img in self.listed_images(pid)}
        cached_map = {
            key: (img.source_url, bool(self.assets.read_bytes(img.local_path)))
            for key, img in existing_rows.items()
        }
        need = set(images_needing_download(wanted, cached_map))
        referer = f"https://{self.store.shop_domain}/"
        identity: list[tuple[bytes, str]] = []
        wanted_keys = {key for key, _src in wanted}

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=4.0), follow_redirects=True) as client:
            for position, img in enumerate(payloads):
                key = image_key(img)
                src = normalize_image_url(str(img.get("src") or img.get("url") or ""))
                cached_row = existing_rows.get(key)
                if key not in need and cached_row:
                    got = self.assets.read_bytes(cached_row.local_path)
                    if got:
                        identity.append(got)
                        continue
                fetched = await fetch_image_bytes(
                    src, referer=referer, shop_domain=self.store.shop_domain, client=client
                )
                if not fetched:
                    if cached_row:
                        stale = self.assets.read_bytes(cached_row.local_path)
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
                    logger.info("ai_ads catalog archive skipped key=%s err=%s", key, err)
                    continue
                saved = self.assets.save_bytes(
                    archived[0],
                    mime_type=archived[1],
                    prefix=f"sku_{pid}",
                )
                image_row = cached_row or ShopifyCatalogImage(
                    store_id=self.store.id,
                    shopify_product_id=pid,
                    image_key=key,
                )
                if not cached_row:
                    self.db.add(image_row)
                old_path = image_row.local_path
                image_row.shopify_image_id = numeric_shopify_id(img.get("id")) or None
                image_row.source_url = src
                image_row.alt = str(img.get("alt") or "") or None
                image_row.position = int(img.get("position") or position)
                image_row.width = img.get("width") if isinstance(img.get("width"), int) else None
                image_row.height = img.get("height") if isinstance(img.get("height"), int) else None
                image_row.local_path = saved["relative_path"]
                image_row.mime_type = archived[1]
                image_row.content_hash = saved["hash"]
                image_row.byte_size = saved["bytes"]
                image_row.last_fetched_at = datetime.now(UTC)
                if old_path and old_path != saved["relative_path"]:
                    self.assets.delete_local(old_path)
                identity.append(archived)

        if identity:
            for key, old in existing_rows.items():
                if key in wanted_keys:
                    continue
                self.assets.delete_local(old.local_path)
                self.db.delete(old)
        else:
            identity = self.cached_identity_bytes(pid)

        row.last_images_fetched_at = datetime.now(UTC)
        self.db.commit()
        return identity[:IDENTITY_LIMIT]

    async def sync_store(self, client: ShopifyClient, *, download_images: bool = True) -> list[dict[str, Any]]:
        products = await client.list_products(limit=100, max_items=100)
        for raw in products:
            self.upsert_product_row(raw)
        self.db.commit()
        if not download_images:
            return products
        for raw in products:
            payloads = product_image_payloads(raw)
            fingerprint = image_fingerprint(payloads)
            pid = numeric_shopify_id(raw.get("id"))
            if self.cached_ready(pid, fingerprint):
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
