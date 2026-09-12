@echo off
chcp 936 >nul
rem 证书续期（给计划任务调用；lego 自己判断是否到期，未到期不会重复签发）
set "DIR=%~dp0"
echo ==== %DATE% %TIME% 续期检查 ==== >> "%DIR%renew.log"
powershell -NoProfile -ExecutionPolicy Bypass -File "%DIR%lego_run.ps1" renew >> "%DIR%renew.log" 2>&1
echo exitcode=%ERRORLEVEL% >> "%DIR%renew.log"
