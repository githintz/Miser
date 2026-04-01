"""
Miser — EU Price Comparison API
FastAPI backend that:
  1. Extracts product details from an Amazon URL (/api/extract)
  2. Searches EEA retailers and returns prices sorted cheapest first (/api/compare)
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

from scrapers import amazon, geizhals, amazon_eu, idealo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Pydantic models ──────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    url: str


class ProductDetails(BaseModel):
    title: str | None = None
    brand: str | None = None
    model: str | None = None
    asin: str | None = None
    image_url: str | None = None
    search_query: str | None = None


class CompareRequest(BaseModel):
    product: ProductDetails
    include_amazon_eu: bool = True
    include_geizhals: bool = True
    include_idealo: bool = True


# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="Miser", description="EU Price Comparison for Swiss Shoppers")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Miser API — see /docs"}


@app.post("/api/extract")
async def extract_product(req: ExtractRequest):
    """
    Step 1: Given an Amazon product URL, return structured product details.
    The user reviews these before triggering the comparison search.
    """
    try:
        product = await amazon.extract_product(req.url)
    except Exception as e:
        logger.error("Amazon extraction failed: %s", e)
        raise HTTPException(status_code=422, detail=f"Could not extract product: {e}")

    if not product.get("title") and not product.get("asin"):
        raise HTTPException(
            status_code=422,
            detail="No product found at this URL. Please check the link and try again.",
        )

    return product


@app.post("/api/compare")
async def compare_prices(req: CompareRequest):
    """
    Step 2: Search EEA retailers and price-comparison sites for the product.
    Returns results sorted from cheapest to most expensive (EUR).
    Non-EUR prices are left as-is but flagged with their currency.
    """
    query = req.product.search_query or req.product.title or ""
    if not query.strip():
        raise HTTPException(status_code=400, detail="Product search query is required.")

    asin = req.product.asin
    tasks = []

    if req.include_amazon_eu:
        tasks.append(amazon_eu.search(query=query, asin=asin))

    if req.include_geizhals:
        tasks.append(geizhals.search(query=query))

    if req.include_idealo:
        tasks.append(idealo.search(query=query))

    # Run all scrapers in parallel
    all_results_nested = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    errors = []
    for r in all_results_nested:
        if isinstance(r, list):
            results.extend(r)
        elif isinstance(r, Exception):
            errors.append(str(r))
            logger.warning("Scraper error: %s", r)

    # Deduplicate by (retailer, price) and clean up
    seen = set()
    unique = []
    for item in results:
        key = (item.get("retailer", ""), item.get("price", 0))
        if key not in seen and item.get("price"):
            seen.add(key)
            unique.append(item)

    # Sort by EUR price ascending (non-EUR items sorted by their numeric price)
    unique.sort(key=lambda x: x.get("price", float("inf")))

    return {
        "query": query,
        "total": len(unique),
        "results": unique,
        "errors": errors,
    }


# Mount static files last so API routes take precedence
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
