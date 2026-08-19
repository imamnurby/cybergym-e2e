#!/usr/bin/env bash

set -euo pipefail

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"

apt-get update >/dev/null
apt-get install -y curl ca-certificates ripgrep fd-find >/dev/null

fdfind_path="$(command -v fdfind || true)"
if [[ -z "$fdfind_path" ]]; then
    echo "Error: fd-find was installed, but fdfind is unavailable" >&2
    exit 1
fi
ln -sfn "$fdfind_path" /usr/local/bin/fd

if ! command -v rg >/dev/null 2>&1; then
    echo "Error: ripgrep was installed, but rg is unavailable" >&2
    exit 1
fi
if ! command -v fd >/dev/null 2>&1; then
    echo "Error: fd symlink is unavailable after installing fd-find" >&2
    exit 1
fi

if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash
fi

source "$NVM_DIR/nvm.sh"
nvm install 22
nvm use 22
npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.84.1

mkdir -p "$HOME/.pi/agent"
