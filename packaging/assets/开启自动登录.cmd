@echo off
chcp 936 >nul
title 开启 Windows 自动登录（让主程序重启后也自动恢复）

echo.
echo   为什么要这一步：
echo     9443 中转 / frp 已经做到"开机就跑、不用登录"了。
echo     但**主程序**必须在"登录后的桌面"里跑 —— 它要驱动 Edge 抓 ERP 数据。
echo     所以想让整台机器重启后**完全无人值守**地恢复，就得让 Windows 自动登录。
echo.
echo   注意：Windows 自动登录会把密码保存在本机注册表里（明文）。
echo         这台电脑只有你自己用、而且必须无人值守，才建议开。
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo   正在申请管理员权限，请在弹窗里点【是】...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'" >nul 2>&1
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0开启自动登录.ps1"
echo.
pause
