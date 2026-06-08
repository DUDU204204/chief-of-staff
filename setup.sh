#!/usr/bin/env bash
# Chief of Staff — first-time setup
# Run from inside the repo: ./setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "🏗  Chief of Staff — setup"
echo

# 1. Python version check
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 not found. Install Python 3.10+ first."
  exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PY_VERSION"

# 2. Create data directory + init DB
mkdir -p data
echo "✓ data/ dir ready"

# 3. Run discovery
echo
echo "🔍 Running auto-discovery..."
python3 discover.py
echo

# 4. Tell user what's next
cat <<'EOF'
─────────────────────────────────────────────
✅ Setup complete!

Next steps:
  1. Start the server:
       python3 server.py

  2. Open the office in your browser:
       http://127.0.0.1:17090

  3. (Optional) Register your own systems:
       cp systems.json.example systems.json
       # edit systems.json
       python3 discover.py

  4. (Optional) Run on boot via LaunchAgent (macOS):
       see docs/launchagent-example.plist
─────────────────────────────────────────────
EOF
