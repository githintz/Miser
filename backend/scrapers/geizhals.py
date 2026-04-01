"""
Search geizhals.eu for a product.
Geizhals is an Austrian price-comparison site covering AT, DE, and EU retailers.
Uses httpx + BeautifulSoup — no browser required.
"""

import re
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import Optional

COUNTRY_VAT = {
    "DE": 0.19, "AT": 0.20, "FR": 0.20, "IT": 0.22, "ES": 0.21,
    "NL": 0.21, "BE": 0.21, "PL": 0.23, "CZ": 0.21, "HU": 0.27,
    "RO": 0.19, "SK": 0.20, "HR": 0.25, "BG": 0.20, "GR": 0.24,
    "SE": 0.25, "DK": 0.25, "FI": 0.25, "PT": 0.23, "IE": 0.23,
}

COUNTRY_FLAGS = {
    "DE": "🇩🇪", "AT": "🇦🇹", "FR": "🇫🇷", "IT": "🇮🇹", "ES": "🇪🇸",
    "NL": "🇳🇱", "BE": "🇧🇪", "PL": "🇵🇱", "CZ": "🇨🇿", "HU": "🇭🇺",
    "RO": "🇷🇴", "SK": "🇸🇰", "HR": "🇭🇷", "BG": "🇧🇬", "GR": "🇬🇷",
    "SE": "🇸🇪", "DK": "🇩🇰", "FI": "🇫🇮", "PT": "🇵🇹", "IE": "🇮🇪",
    "CH": "🇨🇭",
}

COUNTRY_NAMES = {
    "DE": "Germany", "AT": "Austria", "FR": "France", "IT": "Italy", "ES": "Spain",
    "NL": "Netherlands", "BE": "Belgium", "PL": "Poland", "CZ": "Czech Republic",
    "HU": "Hungary", "RO": "Romania", "SK": "Slovakia", "HR": "Croatia",
    "BG": "Bulgaria", "GR": "Greece", "SE": "Sweden", "DK": "Denmark",
    "FI": "Finland", "PT": "Portugal", "IE": "Ireland", "CH": "Switzerland",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-AT,de;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    cleaned = re.sub(r"[€\s\xa0\u202f]", "", text)
    # European format: 1.234,56
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


def _detect_country(retailer: str, url: str) -> str:
    text = (retailer + " " + (url or "")).lower()
    tld_map = [
        (".de", "DE"), (".at", "AT"), (".fr", "FR"), (".it", "IT"), (".es", "ES"),
        (".nl", "NL"), (".be", "BE"), (".pl", "PL"), (".cz", "CZ"), (".hu", "HU"),
        (".ro", "RO"), (".sk", "SK"), (".hr", "HR"), (".bg", "BG"), (".gr", "GR"),
        (".se", "SE"), (".dk", "DK"), (".fi", "FI"), (".pt", "PT"), (".ie", "IE"),
        (".ch", "CH"),
    ]
    for tld, cc in sorted(tld_map, key=lambda x: -len(x[0])):
        if tld in text:
            return cc
    return "DE"


async def _get_product_url(client: httpx.AsyncClient, query: str) -> Optional[str]:
    """Search geizhals and return the URL of the best-matching product page."""
    search_url = f"https://geizhals.eu/?fs={query.replace(' ', '+')}&in=eu"
    try:
        resp = await client.get(search_url, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "lxml")

        # If geizhals redirects directly to a product page
        if "/preisvergleich/" in str(resp.url) or "/pv" in str(resp.url):
            return str(resp.url)

        # Otherwise find first product link in search results
        for a in soup.select("a[href*='/preisvergleich/'], a[href*='/?a=']"):
            href = a.get("href", "")
            if href.startswith("/"):
                return "https://geizhals.eu" + href
            if href.startswith("https://geizhals"):
                return href
    except Exception:
        pass
    return None


async def _scrape_offers(client: httpx.AsyncClient, product_url: str, max_results: int) -> list[dict]:
    """Scrape price offers from a Geizhals product page."""
    results = []
    try:
        resp = await client.get(product_url, timeout=15)
        if resp.status_code != 200:
            return results
        soup = BeautifulSoup(resp.text, "lxml")

        # Geizhals offer rows — multiple possible selectors across their page versions
        offer_rows = (
            soup.select(".offerlist-item")
            or soup.select("tr.offer")
            or soup.select("[class*='offer-list'] li")
            or soup.select("table.offers tbody tr")
        )

        for row in offer_rows[:max_results]:
            try:
                # Retailer name
                retailer_el = (
                    row.select_one(".merchant-name")
                    or row.select_one(".shop a")
                    or row.select_one("a[class*='merchant']")
                    or row.select_one("td.merchant")
                )
                retailer = retailer_el.get_text(strip=True) if retailer_el else None

                # Price
                price_el = (
                    row.select_one(".price")
                    or row.select_one("[class*='preis']")
                    or row.select_one("td.price")
                    or row.select_one("[class*='price-amount']")
                )
                price_text = price_el.get_text(strip=True) if price_el else None
                price = _parse_price(price_text) if price_text else None

                # Link to offer
                link_el = (
                    row.select_one("a[href*='goto'], a[href*='merchant']")
                    or row.select_one("a.merchant-name")
                )
                href = link_el.get("href") if link_el else None
                offer_url = ("https://geizhals.eu" + href) if href and href.startswith("/") else href

                if retailer and price:
                    country = _detect_country(retailer, offer_url or "")
                    vat = COUNTRY_VAT.get(country, 0.20)
                    results.append({
                        "retailer": retailer,
                        "country": country,
                        "flag": COUNTRY_FLAGS.get(country, "🏳"),
                        "country_name": COUNTRY_NAMES.get(country, country),
                        "price": price,
                        "currency": "EUR",
                        "vat_rate": vat,
                        "price_excl_vat": round(price / (1 + vat), 2),
                        "url": offer_url or product_url,
                        "in_stock": True,
                        "source": "geizhals.eu",
                        "title": None,
                    })
            except Exception:
                continue
    except Exception:
        pass
    return results


async def search(query: str, max_results: int = 20) -> list[dict]:
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        product_url = await _get_product_url(client, query)
        if not product_url:
            return []
        return await _scrape_offers(client, product_url, max_results)
