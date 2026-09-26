@echo off
title Book AI Worker
cd /d "%~dp0"
echo Starting Book AI background worker...
echo This processes uploaded books of any size automatically.
echo Keep this window open. Press Ctrl+C to stop.
echo.
python worker.py
pause
