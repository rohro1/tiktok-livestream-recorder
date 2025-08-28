#!/bin/bash
set -e

echo "=== Step 1: Remove old virtual environment ==="
rm -rf .venv

echo "=== Step 2: Remove old Python caches ==="
find . -type d -name "__pycache__" -exec rm -rf {} +

echo "=== Step 3: Reinstall dependencies ==="
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip first
pip install --upgrade pip

# Install fresh from requirements.txt
pip install -r requirements.txt

echo "=== Step 4: Confirm installed packages ==="
pip list

echo "=== Step 5: Force Render to pick up new files ==="
git add .
git commit -m "Force update all files"
git push origin main

echo "=== Done! Now Render should rebuild with updated scripts ==="
