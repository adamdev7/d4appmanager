from __future__ import annotations

import re
from typing import Any

from app.services.ai_ads.schemas import ProductContext, ProductImage, ProductVariant


def normalize_product(
    product: dict[str, Any],
    *,
    shop_domain: str | None = None,
    currency: str | None = None,
    brand_name: str | None = None,
) -> ProductContext:
    """Normalize a Shopify product payload. Never invent specs not present in the payload."""
    pid = str(product.get("id") or "")
    title = str(product.get("title") or "").strip()
    body = _strip_html(str(product.get("body_html") or product.get("description") or ""))
    handle = str(product.get("handle") or "").strip()
    domain = (shop_domain or "").replace("https://", "").replace("http://", "").strip("/")
    url = None
    if domain and handle:
        url = f"https://{domain}/products/{handle}"
    elif product.get("online_store_url"):
        url = str(product.get("online_store_url"))

    images: list[ProductImage] = []
    for img in product.get("images") or []:
        if not isinstance(img, dict):
            continue
        src = str(img.get("src") or img.get("url") or "").strip() or None
        if not src:
            continue
        images.append(
            ProductImage(
                src=src,
                alt=str(img.get("alt") or title) or None,
                width=_int(img.get("width")),
                height=_int(img.get("height")),
            )
        )
    if not images and isinstance(product.get("image"), dict):
        src = str(product["image"].get("src") or "").strip() or None
        if src:
            images.append(ProductImage(src=src, alt=title or None))

    variants: list[ProductVariant] = []
    prices: list[float] = []
    for var in product.get("variants") or []:
        if not isinstance(var, dict):
            continue
        price_s = str(var.get("price") or "") or None
        price_f = _float(var.get("price"))
        if price_f is not None:
            prices.append(price_f)
        variants.append(
            ProductVariant(
                id=str(var.get("id") or "") or None,
                title=str(var.get("title") or "") or None,
                price=price_s,
                sku=str(var.get("sku") or "") or None,
                available=var.get("available") if isinstance(var.get("available"), bool) else None,
            )
        )

    collections: list[str] = []
    for col in product.get("collections") or []:
        if isinstance(col, dict) and col.get("title"):
            collections.append(str(col["title"]))
        elif isinstance(col, str):
            collections.append(col)
    ptype = str(product.get("product_type") or "").strip()
    vendor = str(product.get("vendor") or brand_name or "").strip()
    tags_raw = product.get("tags") or []
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    else:
        tags = [str(t) for t in tags_raw if t]

    restrictions: list[str] = [
        "Do not invent ingredients, materials, guarantees, discounts, or benefits that are not in this product data."
    ]
    if not body:
        restrictions.append("Product description is empty; do not fabricate one.")

    brand_context: dict[str, Any] = {}
    if vendor:
        brand_context["vendor"] = vendor
    if ptype:
        brand_context["product_type"] = ptype
    if tags:
        brand_context["tags"] = tags

    return ProductContext(
        product_id=pid,
        title=title or "Untitled product",
        description=body,
        price=min(prices) if prices else _float(product.get("price")),
        currency=currency,
        product_url=url,
        images=images,
        variants=variants,
        collections=collections,
        brand_context=brand_context,
        target_market={},
        restrictions=restrictions,
    )


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
