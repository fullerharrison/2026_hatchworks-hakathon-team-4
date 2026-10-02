@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Please ask your team to install uv, then double-click this file again.
  pause
  exit /b 1
)
echo Starting your breeder review in a separate practice session.
echo Your browser will open automatically. Keep this window open during the review.
echo Read app\HUMAN_REVIEW.md for the short review steps.
uv run --locked --project app python scripts/review_session.py --participant breeder-review --condition no-defaults --open-browser
if errorlevel 1 pause
