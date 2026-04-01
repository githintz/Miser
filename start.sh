#!/usr/bin/env bash
# Miser — startup script
# Run this once to install dependencies, then starts the server.

set -e
cd "$(dirname "$0")/backend"

echo "🔍 Miser — EU Price Comparison for Swiss Shoppers"
echo "=================================================="

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 is required. Install from https://python.org"
  exit 1
fi

# Create venv if needed
if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "→ Installing Python dependencies..."
pip install -q -r requirements.txt

# Install Playwright browsers (only Chromium needed)
echo "→ Installing Playwright browsers (first time only)..."
playwright install chromium --with-deps 2>/dev/null || playwright install chromium

echo ""
echo "✅ Ready! Starting Miser on http://localhost:8000"
echo "   Open http://localhost:8000 in your browser."
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
