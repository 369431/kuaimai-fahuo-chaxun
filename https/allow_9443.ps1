# -*- coding: utf-8 -*-
# 放行 9443（手机 HTTPS 入口）。不是管理员时自动弹 UAC 提权，双击即可。
# 说明：netsh 的输出不做管道解析（某些环境下 Out-String 会抛 SwitchParameter 转换错），
#       改为 Start-Process 重定向到临时文件 + Get-NetFirewallRule 双保险。
param([switch]$Check)

$Rule = 'KuaimaiScan Web HTTPS (TCP 9443)'
$NetArgsAdd = @('advfirewall', 'firewall', 'add', 'rule', "name=$Rule", 'dir=in',
    'action=allow', 'protocol=TCP', 'localport=9443', 'profile=any')
$NetArgsShow = @('advfirewall', 'firewall', 'show', 'rule', "name=$Rule")

function Test-RulePresent {
  try {
    $pf = Get-NetFirewallRule -DisplayName $Rule -ErrorAction Stop | Get-NetFirewallPortFilter -ErrorAction Stop
    foreach ($p in @($pf)) { if ("$($p.LocalPort)" -match '9443') { return $true } }
  } catch { }
  try {
    $tmp = Join-Path $env:TEMP 'km_fw9443.txt'
    Start-Process -FilePath 'netsh.exe' -ArgumentList $NetArgsShow -NoNewWindow -Wait `
      -RedirectStandardOutput $tmp -RedirectStandardError ($tmp + '.err') | Out-Null
    if ((Get-Content $tmp -Raw -ErrorAction SilentlyContinue) -match '9443') { return $true }
  } catch { }
  return $false
}

if ($Check) {
  Write-Host ("规则名： " + $Rule)
  Write-Host ("将执行： netsh " + ($NetArgsAdd -join ' '))
  Write-Host ("当前是否存在： " + (Test-RulePresent))
  exit 0
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host ''
  Write-Host '  需要管理员权限，正在弹出授权窗口 —— 请在弹窗里点「是」。' -ForegroundColor Yellow
  Write-Host ''
  Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"')
  )
  Start-Sleep -Seconds 2
  exit 0
}

Write-Host ''
Write-Host '  正在放行 TCP 9443 ...' -ForegroundColor Cyan
Start-Process -FilePath 'netsh.exe' -ArgumentList $NetArgsAdd -NoNewWindow -Wait `
  -RedirectStandardOutput ($env:TEMP + '\km_fw9443_add.out') `
  -RedirectStandardError ($env:TEMP + '\km_fw9443_add.err') | Out-Null
Start-Sleep -Milliseconds 800

if (Test-RulePresent) {
  Write-Host '  [OK] 9443 已放行' -ForegroundColor Green
  Write-Host ''
  Write-Host '  手机地址： https://shsp.pw:9443/' -ForegroundColor Green
} else {
  Write-Host '  [x] 没查到规则，请把下面两行截图发我：' -ForegroundColor Red
  foreach ($f in @('\km_fw9443_add.out', '\km_fw9443_add.err')) {
    $p = $env:TEMP + $f
    if (Test-Path $p) { Write-Host ("  " + $f + " -> " + ((Get-Content $p -Raw) -replace '\s+$', '')) }
  }
}
Write-Host ''
Write-Host '  按回车关闭本窗口...' -NoNewline
Read-Host | Out-Null
