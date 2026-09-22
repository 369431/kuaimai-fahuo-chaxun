# 下载 frpc.exe（第三方二进制，不入库）到 packaging\frp\
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging\download_frp.ps1
#
# 为什么不入库：frp 是 fatedier/frp 的第三方发布物，13 MB 二进制，跟本项目源码无关。
# 版本要对齐客户端自述的版本（本机实测 frpc --version = 0.71.0）。
param(
    [string]$FrpVersion = "0.71.0"
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Here = $PSScriptRoot
$Dst = Join-Path $Here 'frp'
New-Item -ItemType Directory -Force -Path $Dst | Out-Null

$asset = "frp_${FrpVersion}_windows_amd64.zip"
$url = "https://github.com/fatedier/frp/releases/download/v${FrpVersion}/${asset}"
$zip = Join-Path $env:TEMP $asset
$tmp = Join-Path $env:TEMP ("frp_" + $FrpVersion + "_x")

Write-Host "[1] 下载 $url"
Invoke-WebRequest $url -OutFile $zip -TimeoutSec 300 -UseBasicParsing
Write-Host ("    完成 {0} MB" -f [math]::Round((Get-Item $zip).Length / 1MB, 2))

Write-Host "[2] 解压取 frpc.exe"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive $zip -DestinationPath $tmp -Force
$found = Get-ChildItem $tmp -Recurse -Filter 'frpc.exe' | Select-Object -First 1
if (-not $found) { throw "解压后没找到 frpc.exe" }
Copy-Item $found.FullName (Join-Path $Dst 'frpc.exe') -Force
Remove-Item $zip -Force -ErrorAction SilentlyContinue

$out = Join-Path $Dst 'frpc.exe'
Write-Host ("[3] 就位 {0}（{1} MB）" -f $out, [math]::Round((Get-Item $out).Length / 1MB, 2))
$ea = $ErrorActionPreference
$ErrorActionPreference = 'Continue'          # frpc --version 往 stderr 写，别被当致命错误
$frpVer = (& $out --version 2>&1 | Select-Object -First 1)
$ErrorActionPreference = $ea
Write-Host ("    自述版本：" + $frpVer)
