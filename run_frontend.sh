#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/frontend"
if [ ! -d node_modules ]; then
  echo "Frontend dependencies missing. Run ../setup_mac.sh first."
  exit 1
fi
exec npm run dev
