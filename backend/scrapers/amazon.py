"""
Extract product details from any Amazon product URL.
Tries structured JSON-LD data first, falls back to HTML parsing.
"""

import re
import json
import httpx
from bs4 import BeautifulSoup
from typing import Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _extract_asin(url: str) -> Optional[str]:
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    return match.group(1) if match else None


def _extract_domain(url: str) -> str:
    """Extract the amazon domain from the URL (e.g. 'www.amazon.de')."""
    m = re.search(r"((?:www\.)?amazon\.[a-z.]+)", url)
    return m.group(1) if m else "www.amazon.com"


def _clean_url(url: str) -> str:
    """Return a minimal /dp/ASIN URL on the original Amazon domain."""
    asin = _extract_asin(url)
    domain = _extract_domain(url)
    if asin:
        return f"https://{domain}/dp/{asin}"
    return url


# Fallback domains to try if the original returns 404/block
_FALLBACK_DOMAINS = [
    "www.amazon.de",
    "www.amazon.fr",
    "www.amazon.co.uk",
    "www.amazon.com",
]


async def extract_product(url: str) -> dict:
    """
    Fetch an Amazon product page and return structured product data.
    Returns dict with keys: title, brand, model, asin, image_url, price, currency, source_url
    """
    asin = _extract_asin(url)
    original_domain = _extract_domain(url)
    # Build ordered list of URLs to try: original domain first, then fallbacks
    domains_to_try = [original_domain] + [d for d in _FALLBACK_DOMAINS if d != original_domain]
    urls_to_try = [f"https://{d}/dp/{asin}" for d in domains_to_try] if asin else [url]

    html = None
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=20) as client:
        for fetch_url in urls_to_try:
            try:
                resp = await client.get(fetch_url)
                if resp.status_code == 200:
                    html = resp.text
                    break
            except Exception:
                continue

    if not html:
        raise RuntimeError(f"Could not fetch product page from any Amazon domain for ASIN {asin}")

    soup = BeautifulSoup(html, "lxml")

    product = {
        "asin": asin,
        "source_url": url,
        "title": None,
        "brand": None,
        "model": None,
        "image_url": None,
        "price": None,
        "currency": None,
    }

    # 1. Try JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0]
            if data.get("@type") in ("Product", "ItemPage"):
                product["title"] = product["title"] or data.get("name")
                product["brand"] = product["brand"] or (
                    data.get("brand", {}).get("name") if isinstance(data.get("brand"), dict)
                    else data.get("brand")
                )
                product["model"] = product["model"] or data.get("model")
                offers = data.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0]
                if offers:
                    product["price"] = product["price"] or offers.get("price")
                    product["currency"] = product["currency"] or offers.get("priceCurrency")
                imgs = data.get("image", [])
                if isinstance(imgs, list) and imgs:
                    product["image_url"] = product["image_url"] or imgs[0]
                elif isinstance(imgs, str):
                    product["image_url"] = product["image_url"] or imgs
        except Exception:
            continue

    # 2. HTML fallbacks
    if not product["title"]:
        title_el = soup.find(id="productTitle") or soup.find("h1", {"id": "title"})
        if title_el:
            product["title"] = title_el.get_text(strip=True)

    if not product["brand"]:
        # Try the byline info bar
        byline = soup.find(id="bylineInfo")
        if byline:
            text = byline.get_text(strip=True)
            # "Brand: Foo" or "Visit the Foo Store"
            m = re.search(r"Brand[:\s]+([^\n]+)", text, re.IGNORECASE)
            if m:
                product["brand"] = m.group(1).strip()
        # Try tech details table
        if not product["brand"]:
            for row in soup.select("#productDetails_techSpec_section_1 tr, #detailBullets_feature_div li"):
                text = row.get_text(" ", strip=True)
                if "brand" in text.lower() or "manufacturer" in text.lower():
                    parts = text.split("‎")
                    if len(parts) > 1:
                        product["brand"] = parts[-1].strip()
                        break

    if not product["model"]:
        for row in soup.select("#productDetails_techSpec_section_1 tr, #detailBullets_feature_div li"):
            text = row.get_text(" ", strip=True)
            if any(kw in text.lower() for kw in ("model number", "item model", "model name")):
                parts = text.split("‎")
                if len(parts) > 1:
                    product["model"] = parts[-1].strip()
                    break

    if not product["image_url"]:
        img = soup.find("img", {"id": "landingImage"}) or soup.find("img", {"id": "imgBlkFront"})
        if img:
            product["image_url"] = img.get("src") or img.get("data-src")

    if not product["price"]:
        price_el = (
            soup.find("span", {"id": "priceblock_ourprice"})
            or soup.find("span", {"id": "priceblock_dealprice"})
            or soup.select_one(".a-price .a-offscreen")
        )
        if price_el:
            raw = price_el.get_text(strip=True)
            m = re.search(r"[\d,\.]+", raw.replace(",", ""))
            if m:
                product["price"] = float(m.group())
            product["currency"] = "USD"

    # Build a clean search query from what we have
    parts = []
    if product["brand"]:
        parts.append(product["brand"])
    if product["model"]:
        parts.append(product["model"])
    elif product["title"]:
        # Use up to 8 words of title
        words = product["title"].split()[:8]
        parts.extend(words)
    product["search_query"] = " ".join(parts) if parts else product["title"] or ""

    return product
