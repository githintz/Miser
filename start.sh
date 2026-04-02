#!/usr/bin/env bash
# Miser — startup script

set -e
cd "$(dirname "$0")/backend"

echo "Miser — EU Price Comparison for Swiss Shoppers"
echo "================================================"

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: Python 3 is required."
  echo "  Ubuntu/WSL:  sudo apt install python3 python3-venv python3-pip"
  echo "  macOS:       brew install python3"
  exit 1
fi

# Check that venv module works (commonly missing on Ubuntu/WSL)
if ! python3 -m venv --help &>/dev/null; then
  echo "ERROR: python3-venv is not installed."
  echo "  Run:  sudo apt install python3-venv"
  exit 1
fi

# Create venv if needed
if [ ! -d ".venv" ]; then
  echo "-> Creating virtual environment..."
  python3 -m venv .venv
fi

# Verify activate script exists (venv creation can silently fail)
if [ ! -f ".venv/bin/activate" ]; then
  echo "ERROR: Virtual environment was not created properly."
  echo "  Try:  sudo apt install python3-venv && rm -rf .venv && ./start.sh"
  exit 1
fi

source .venv/bin/activate

echo "-> Installing Python dependencies..."
pip install -q -r requirements.txt

echo ""
echo "Ready! Starting Miser on http://localhost:8000"
echo "Open http://localhost:8000 in your browser."
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
