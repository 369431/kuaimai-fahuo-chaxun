@echo off
rem Start the latest (source) build of 快麦扫码查询, which includes the new "打单" button.
cd /d "%~dp0"
start "" pythonw desktop\kuaimai_scan.py
exit /b 0
