#!/usr/bin/env bash

set -euo pipefail

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"

apt-get update >/dev/null
apt-get install -y curl ca-certificates >/dev/null

if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash
fi

source "$NVM_DIR/nvm.sh"
nvm install 22
nvm use 22
npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.84.1

mkdir -p "$HOME/.pi/agent"
