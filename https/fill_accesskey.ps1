# -*- coding: utf-8 -*-
# 引导把阿里云 AccessKey 填进两个 txt，然后校验（不打印密钥内容）
param([switch]$Check)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Ak = Join-Path $Root 'aliyun\access_key.txt'
$Sk = Join-Path $Root 'aliyun\access_key_secret.txt'

function Test-Cred {
  $ok = $true
  foreach ($pair in @(@{ f = $Ak; n = 'AccessKey ID' }, @{ f = $Sk; n = 'AccessKey Secret' })) {
    $f = $pair.f
    if (-not (Test-Path $f)) { Write-Host "  [x] 找不到文件：$f" -ForegroundColor Red; $ok = $false; continue }
    $v = (Get-Content $f -Raw).Trim()
    if (-not $v) {
      Write-Host "  [x] $($pair.n) 还是空的：$f" -ForegroundColor Red; $ok = $false
    } elseif ($v -match 'PASTE_') {
      Write-Host "  [x] $($pair.n) 还是占位文字，没换成你的密钥" -ForegroundColor Red; $ok = $false
    } else {
      Write-Host "  [v] $($pair.n) 已填写（$($v.Length) 个字符）" -ForegroundColor Green
    }
  }
  return $ok
}

if (-not $Check) {
  Write-Host ''
  Write-Host '  ============================================================' -ForegroundColor Cyan
  Write-Host '    第 1 步：把阿里云 AccessKey 填进下面这两个文件' -ForegroundColor Cyan
  Write-Host '  ============================================================' -ForegroundColor Cyan
  Write-Host ''
  Write-Host '    文件位置：' -ForegroundColor Gray
  Write-Host "      $Ak" -ForegroundColor Gray
  Write-Host "      $Sk" -ForegroundColor Gray
  Write-Host ''
  Write-Host '    马上会弹出两个记事本：'
  Write-Host '      第 1 个   access_key.txt         粘贴【AccessKey ID】'
  Write-Host '      第 2 个   access_key_secret.txt  粘贴【AccessKey Secret】'
  Write-Host ''
  Write-Host '    怎么做：'
  Write-Host '      1) 把文件里原有的那行英文占位文字【整行删掉】'
  Write-Host '      2) 粘贴你的密钥（只留一行，前后不要有空格）'
  Write-Host '      3) Ctrl+S 保存，然后关掉记事本'
  Write-Host ''
  Write-Host '    准备好了按回车，我就打开这两个记事本...' -NoNewline
  Read-Host | Out-Null
  Start-Process notepad.exe $Ak
  Start-Process notepad.exe $Sk
  Write-Host ''
  Write-Host '    两个记事本都保存并关闭后，回到本窗口按回车，我来检查。' -NoNewline
  Read-Host | Out-Null
}

Write-Host ''
$ok = Test-Cred
Write-Host ''
if ($ok) {
  Write-Host '  === 两个文件都填好了，可以签发证书了 ===' -ForegroundColor Green
} else {
  Write-Host '  === 还没填好 ===' -ForegroundColor Yellow
  Write-Host ''
  Write-Host '  如果还没有 AccessKey，去阿里云控制台申请：' -ForegroundColor Yellow
  Write-Host '    访问控制 RAM  ->  用户  ->  创建用户（勾选「OpenAPI 访问」）' -ForegroundColor Yellow
  Write-Host '    授权策略只勾选：AliyunDNSFullAccess' -ForegroundColor Yellow
  Write-Host '    创建完成后就能看到 AccessKey ID 和 AccessKey Secret' -ForegroundColor Yellow
}
Write-Host ''
if (-not $Check) { Write-Host '  按回车关闭本窗口...' -NoNewline; Read-Host | Out-Null }
if ($ok) { exit 0 } else { exit 1 }
