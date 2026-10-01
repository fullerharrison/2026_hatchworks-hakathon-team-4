@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Install uv from https://docs.astral.sh/uv/getting-started/installation/ then try again.
  pause
  exit /b 1
)
echo Preparing the dashboard. First launch downloads Python and dependencies if needed.
echo Keep this window open while using the app. Press Ctrl+C to stop.
uv run --locked --project app uc4-ask serve --open-browser
if errorlevel 1 pause
