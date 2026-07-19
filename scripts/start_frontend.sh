#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../frontend"

if [ ! -d "node_modules" ]; then
  npm ci
fi

npm run dev
