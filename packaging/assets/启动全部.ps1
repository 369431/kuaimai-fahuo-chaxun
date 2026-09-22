$ErrorActionPreference = 'SilentlyContinue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Join-Path $dir '快麦扫码查询.exe'
$mid = Join-Path $dir 'kuaimai_https\km_https.exe'
$midpy = Join-Path $dir 'kuaimai_https\km_https.py'
if (Test-Path $app) { Start-Process -FilePath $app -WorkingDirectory $dir }
Start-Sleep -Seconds 3
if (Test-Path $mid) { Start-Process -FilePath $mid -WorkingDirectory (Join-Path $dir 'kuaimai_https') -WindowStyle Hidden }
elseif (Test-Path $midpy) { Start-Process -FilePath 'pythonw' -ArgumentList ('"' + $midpy + '"') -WorkingDirectory (Join-Path $dir 'kuaimai_https') -WindowStyle Hidden }
