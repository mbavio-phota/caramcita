#!/bin/zsh
# Corre desde la Mac (IP residencial) las fuentes con run_from: mac y Zonaprop, y sube los snapshots.
# Lo llama launchd; ver launchd/README.md.
set -euo pipefail
REPO="${CARAMCITA_REPO:-$HOME/dev/mrbavio/caramcita}"
cd "$REPO"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
git pull -q --rebase --autostash || true
.venv/bin/caramcita snapshot --mac zonaprop || true
git add snapshots/*.json
if git diff --cached --quiet; then exit 0; fi
git commit -q -m "snapshot zonaprop $(date +'%Y-%m-%d %H:%M')"
git push -q || (git pull -q --rebase && git push -q)
