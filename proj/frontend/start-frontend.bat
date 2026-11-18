@echo off
cd /d "%~dp0"
if not exist node_modules call npm install --legacy-peer-deps
npm run dev
