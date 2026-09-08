#!/bin/zsh
# Corre Zonaprop con navegador desde la Mac (IP residencial) y sube el snapshot al repo.
# Lo llama launchd; ver launchd/README.md.
set -euo pipefail
REPO="${CARAMCITA_REPO:-$HOME/dev/mrbavio/caramcita}"
cd "$REPO"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
git pull -q --rebase --autostash || true
.venv/bin/caramcita snapshot zonaprop
git add snapshots/zonaprop.json
if git diff --cached --quiet; then exit 0; fi
git commit -q -m "snapshot zonaprop $(date +'%Y-%m-%d %H:%M')"
git push -q || (git pull -q --rebase && git push -q)
