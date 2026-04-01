"""
Search idealo across EU locales.
Uses httpx + BeautifulSoup. Idealo is partially server-rendered.
Tries to find the internal search JSON endpoint first, falls back to HTML parsing.
"""

import re
import json
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import Optional

COUNTRY_INFO = {
    "de": {"name": "Germany",      "flag": "🇩🇪", "vat": 0.19, "currency": "EUR"},
    "at": {"name": "Austria",      "flag": "🇦🇹", "vat": 0.20, "currency": "EUR"},
    "fr": {"name": "France",       "flag": "🇫🇷", "vat": 0.20, "currency": "EUR"},
    "it": {"name": "Italy",        "flag": "🇮🇹", "vat": 0.22, "currency": "EUR"},
    "es": {"name": "Spain",        "flag": "🇪🇸", "vat": 0.21, "currency": "EUR"},
    "nl": {"name": "Netherlands",  "flag": "🇳🇱", "vat": 0.21, "currency": "EUR"},
    "pl": {"name": "Poland",       "flag": "🇵🇱", "vat": 0.23, "currency": "PLN"},
    "se": {"name": "Sweden",       "flag": "🇸🇪", "vat": 0.25, "currency": "SEK"},
    "dk": {"name": "Denmark",      "flag": "🇩🇰", "vat": 0.25, "currency": "DKK"},
    "fi": {"name": "Finland",      "flag": "🇫🇮", "vat": 0.25, "currency": "EUR"},
    "pt": {"name": "Portugal",     "flag": "🇵🇹", "vat": 0.23, "currency": "EUR"},
    "ie": {"name": "Ireland",      "flag": "🇮🇪", "vat": 0.23, "currency": "EUR"},
}

IDEALO_LOCALES = [
    ("de", "https://www.idealo.de"),
    ("at", "https://www.idealo.at"),
    ("fr", "https://www.idealo.fr"),
    ("it", "https://www.idealo.it"),
    ("es", "https://www.idealo.es"),
    ("nl", "https://www.idealo.nl"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    cleaned = re.sub(r"[€£\s\xa0\u202f]", "", text)
    if re.search(r"\d\.\d{3},\d{2}", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    m = re.search(r"\d+\.\d+|\d+", cleaned)
    try:
        return float(m.group()) if m else None
    except ValueError:
        return None


async def _search_one_locale(
    client: httpx.AsyncClient,
    country_code: str,
    base_url: str,
    query: str,
    max_results: int,
) -> list[dict]:
    results = []
    info = COUNTRY_INFO[country_code]
    search_url = f"{base_url}/preisvergleich/MainSearchProductCategory.html?q={query.replace(' ', '+')}"

    try:
        resp = await client.get(search_url, timeout=15)
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "lxml")

        # Try JSON-LD (idealo embeds product data in structured data)
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "ItemList":
                        for entry in (item.get("itemListElement") or [])[:max_results]:
                            product = entry.get("item") or entry
                            name = product.get("name")
                            offers = product.get("offers", {})
                            if isinstance(offers, list):
                                offers = offers[0]
                            price = None
                            url = product.get("url")
                            if offers:
                                try:
                                    price = float(offers.get("price", 0))
                                except (TypeError, ValueError):
                                    pass
                                url = url or offers.get("url")
                            if name and price:
                                results.append({
                                    "retailer": f"idealo.{country_code} — {name[:50]}",
                                    "country": country_code.upper(),
                                    "flag": info["flag"],
                                    "country_name": info["name"],
                                    "price": price,
                                    "currency": info["currency"],
                                    "vat_rate": info["vat"],
                                    "price_excl_vat": round(price / (1 + info["vat"]), 2),
                                    "url": url or search_url,
                                    "in_stock": True,
                                    "source": f"idealo.{country_code}",
                                    "title": name,
                                })
                    elif item.get("@type") == "Product":
                        name = item.get("name")
                        offers = item.get("offers", {})
                        if isinstance(offers, list):
                            offers = offers[0]
                        price = None
                        url = item.get("url")
                        if offers:
                            try:
                                price = float(offers.get("price", 0))
                            except (TypeError, ValueError):
                                pass
                        if name and price:
                            results.append({
                                "retailer": f"idealo.{country_code} — {name[:50]}",
                                "country": country_code.upper(),
                                "flag": info["flag"],
                                "country_name": info["name"],
                                "price": price,
                                "currency": info["currency"],
                                "vat_rate": info["vat"],
                                "price_excl_vat": round(price / (1 + info["vat"]), 2),
                                "url": url or search_url,
                                "in_stock": True,
                                "source": f"idealo.{country_code}",
                                "title": name,
                            })
                        break
            except Exception:
                continue

        # HTML fallback — look for price cards in the search results
        if not results:
            cards = soup.select(
                ".sr-resultList__item, .offerList-item, "
                "[class*='resultItem'], [class*='product-item']"
            )
            for card in cards[:max_results]:
                title_el = card.select_one(
                    "a[class*='title'], [class*='productTitle'], h2, h3"
                )
                price_el = card.select_one(
                    "[class*='idealPrice'], [class*='price'], [class*='Price']"
                )
                link_el = card.select_one("a[href]")
                title = title_el.get_text(strip=True) if title_el else None
                price_text = price_el.get_text(strip=True) if price_el else None
                price = _parse_price(price_text) if price_text else None
                href = link_el.get("href") if link_el else None
                url = (base_url + href) if href and href.startswith("/") else href

                if title and price:
                    results.append({
                        "retailer": f"idealo.{country_code} — {title[:50]}",
                        "country": country_code.upper(),
                        "flag": info["flag"],
                        "country_name": info["name"],
                        "price": price,
                        "currency": info["currency"],
                        "vat_rate": info["vat"],
                        "price_excl_vat": round(price / (1 + info["vat"]), 2),
                        "url": url or search_url,
                        "in_stock": True,
                        "source": f"idealo.{country_code}",
                        "title": title,
                    })

    except Exception:
        pass

    return results[:max_results]


async def search(query: str, max_results_per_locale: int = 3) -> list[dict]:
    all_results = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        tasks = [
            _search_one_locale(client, cc, base, query, max_results_per_locale)
            for cc, base in IDEALO_LOCALES
        ]
        locale_results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in locale_results:
            if isinstance(r, list):
                all_results.extend(r)
    return all_results
