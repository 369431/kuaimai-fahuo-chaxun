@echo off
chcp 936 >nul
title 注册真·开机自启（快麦扫码查询）

rem ── 检查是不是管理员；不是就自己弹 UAC 重新运行 ─────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   需要管理员权限才能注册"开机就跑、不用登录"的计划任务。
    echo   正在申请提权，请在弹窗里点【是】...
    echo.
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'" >nul 2>&1
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0注册真开机自启.ps1"
echo.
pause
