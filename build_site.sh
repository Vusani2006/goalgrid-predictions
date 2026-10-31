#!/usr/bin/env bash
set -euo pipefail
mkdir -p dist
cp index.html styles.css favicon.svg data.js backtest_data.js script.js config.js vip.js dist/
# Do not ship SQL, Python, Github Actions or API keys as public assets.
