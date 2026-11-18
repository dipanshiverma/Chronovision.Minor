#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -d node_modules ] || npm install --legacy-peer-deps
npm run dev
