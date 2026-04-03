"""
Search Amazon EU marketplaces (DE, FR, IT, ES, NL) for a product by ASIN or query.
Amazon EU prices include local VAT by default.
"""

import re
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import Optional

MARKETPLACES = [
    ("DE", "🇩🇪", "Germany", "https://www.amazon.de", "EUR", 0.19),
    ("FR", "🇫🇷", "France", "https://www.amazon.fr", "EUR", 0.20),
    ("IT", "🇮🇹", "Italy", "https://www.amazon.it", "EUR", 0.22),
    ("ES", "🇪🇸", "Spain", "https://www.amazon.es", "EUR", 0.21),
    ("NL", "🇳🇱", "Netherlands", "https://www.amazon.nl", "EUR", 0.21),
    ("SE", "🇸🇪", "Sweden", "https://www.amazon.se", "SEK", 0.25),
    ("PL", "🇵🇱", "Poland", "https://www.amazon.pl", "PLN", 0.23),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    # Remove currency symbols, spaces, &nbsp;
    cleaned = re.sub(r"[^\d,\.]", "", text)
    # European format detection
    if re.search(r"\d\.\d{3},\d{2}", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


async def _fetch_by_asin(
    client: httpx.AsyncClient,
    country: str,
    flag: str,
    country_name: str,
    base_url: str,
    currency: str,
    vat: float,
    asin: str,
) -> Optional[dict]:
    """Fetch a product page by ASIN on a specific Amazon marketplace."""
    url = f"{base_url}/dp/{asin}"
    try:
        resp = await client.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "lxml")

        title_el = soup.find(id="productTitle")
        title = title_el.get_text(strip=True) if title_el else None

        # Try multiple price selectors
        price = None
        for sel in [
            ".a-price .a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#apex_offerDisplay_desktop .a-price .a-offscreen",
            "#corePrice_desktop .a-price .a-offscreen",
            ".priceToPay .a-offscreen",
        ]:
            el = soup.select_one(sel)
            if el:
                price = _parse_price(el.get_text(strip=True))
                if price:
                    break

        if not price:
            return None

        return {
            "retailer": f"Amazon {country}",
            "country": country,
            "flag": flag,
            "country_name": country_name,
            "price": price,
            "currency": currency,
            "vat_rate": vat,
            "price_excl_vat": round(price / (1 + vat), 2),
            "url": url,
            "in_stock": True,
            "source": f"amazon.{country.lower()}",
            "title": title,
        }
    except Exception:
        return None


async def _search_by_query(
    client: httpx.AsyncClient,
    country: str,
    flag: str,
    country_name: str,
    base_url: str,
    currency: str,
    vat: float,
    query: str,
) -> Optional[dict]:
    """Search Amazon marketplace and return the first result's price."""
    search_url = f"{base_url}/s?k={query.replace(' ', '+')}"
    try:
        resp = await client.get(search_url, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "lxml")

        # Find first result with a price
        for item in soup.select("[data-component-type='s-search-result']"):
            title_el = item.select_one("h2 a span")
            price_el = item.select_one(".a-price .a-offscreen")
            link_el = item.select_one("h2 a")

            if not (price_el and link_el):
                continue

            price = _parse_price(price_el.get_text(strip=True))
            if not price:
                continue

            href = link_el.get("href", "")
            url = base_url + href if href.startswith("/") else href

            return {
                "retailer": f"Amazon {country}",
                "country": country,
                "flag": flag,
                "country_name": country_name,
                "price": price,
                "currency": currency,
                "vat_rate": vat,
                "price_excl_vat": round(price / (1 + vat), 2),
                "url": url,
                "in_stock": True,
                "source": f"amazon.{country.lower()}",
                "title": title_el.get_text(strip=True) if title_el else None,
            }
    except Exception:
        pass
    return None


async def search(query: str, asin: Optional[str] = None) -> list[dict]:
    """
    Search all Amazon EU marketplaces.
    If an ASIN is provided, tries direct ASIN lookup first on every marketplace.
    For any marketplace where ASIN lookup returns nothing, falls back to keyword search.
    This handles US ASINs that may not exist on all EU stores.
    """
    results = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        # Step 1: ASIN lookup across all marketplaces (if ASIN available)
        if asin:
            asin_tasks = [
                _fetch_by_asin(client, country, flag, country_name, base_url, currency, vat, asin)
                for country, flag, country_name, base_url, currency, vat in MARKETPLACES
            ]
            asin_results = await asyncio.gather(*asin_tasks, return_exceptions=True)
            found_countries = set()
            for r in asin_results:
                if isinstance(r, dict):
                    results.append(r)
                    found_countries.add(r["country"])
        else:
            found_countries = set()

        # Step 2: Keyword search for any marketplace that didn't return an ASIN hit
        remaining = [
            (country, flag, country_name, base_url, currency, vat)
            for country, flag, country_name, base_url, currency, vat in MARKETPLACES
            if country not in found_countries
        ]
        if remaining:
            query_tasks = [
                _search_by_query(client, country, flag, country_name, base_url, currency, vat, query)
                for country, flag, country_name, base_url, currency, vat in remaining
            ]
            query_results = await asyncio.gather(*query_tasks, return_exceptions=True)
            for r in query_results:
                if isinstance(r, dict):
                    results.append(r)

    return results
