# Miser — EU Price Comparison for Swiss Shoppers

Find the cheapest price across Europe for any Amazon product.

## How it works

1. **Paste an Amazon link** — any Amazon storefront (.com, .de, .co.uk, etc.)
2. **Confirm the product details** — review/edit the extracted title, brand, and model
3. **Get a price comparison** — Miser searches:
   - Amazon EU marketplaces: DE, FR, IT, ES, NL, SE, PL
   - Geizhals.eu (EU-wide price aggregator covering hundreds of retailers)
4. **Results are sorted cheapest first**, with VAT rates shown per country

## Quick Start

```bash
chmod +x start.sh
./start.sh
```

Then open **http://localhost:8000** in your browser.

### Requirements

- Python 3.11+
- ~200 MB disk space for Playwright's Chromium browser (downloaded once on first run)

## Why EU prices are often cheaper for Swiss buyers

- EU VAT rates (19–27%) are often lower than Swiss markups
- Countries like Germany (19% VAT) can be significantly cheaper than Switzerland
- Retailers like MediaMarkt DE, Amazon DE, etc. often ship to Switzerland

**Note:** All prices shown include local VAT. Shipping costs to Switzerland are not included — check each retailer's shipping policy. For orders over CHF 65, Swiss customs duties may apply.

## Architecture

```
backend/
  main.py              FastAPI app + static file server
  scrapers/
    amazon.py          Extracts product info from Amazon URL
    amazon_eu.py       Searches Amazon DE/FR/IT/ES/NL/SE/PL
    geizhals.py        Searches geizhals.eu (EU price aggregator)
    idealo.py          Searches idealo across EU locales
frontend/
  index.html           Single-page app
  style.css            Styles
  app.js               Frontend logic
```
