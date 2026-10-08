# ============================================================================
#  注册「真·开机自启」—— 需要管理员（会弹 UAC）
#
#  跟老的「装开机自启.ps1」的区别：
#    老版：全部 -AtLogOn            → 重启后停在登录界面，什么都不会起 ✗
#    新版：中转/隧道 用 -AtStartup + SYSTEM → **没人登录也跑** ✓
#          主程序  用 -AtLogOn + 当前用户 → 它要驱动 Edge，必须有桌面 ✓
#          再加一个看门狗，每 3 分钟巡检，谁挂了拉谁 ✓
#
#  任务清单：
#    KuaimaiHTTPS     开机(无需登录) SYSTEM     km_https.exe --port 9443
#    KuaimaiFrpc      开机(无需登录) SYSTEM     frpc -c frpc.toml
#    KuaimaiScan App  登录            当前用户   快麦扫码查询.exe
#    KuaimaiWatchdog  每 3 分钟 · 无限期 SYSTEM  看门狗.ps1
# ============================================================================
$ErrorActionPreference = 'SilentlyContinue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$app  = Join-Path $dir '快麦扫码查询.exe'
$mid  = Join-Path $dir 'kuaimai_https\km_https.exe'
$frpc = Join-Path $dir 'frp\frpc.exe'
$fcfg = Join-Path $dir 'frp\frpc.toml'
$dog  = Join-Path $dir '看门狗.ps1'

function Need-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host ''
        Write-Host '  这个脚本需要【管理员权限】才能注册"开机就跑（不用登录）"的计划任务。' -ForegroundColor Yellow
        Write-Host '  请右键 → 以管理员身份运行，或直接双击「注册真开机自启.cmd」（它会自动弹 UAC）。' -ForegroundColor Yellow
        Write-Host ''
        exit 1
    }
}
Need-Admin

$sys = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$setInf = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
            -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable

Write-Host ''
Write-Host '=== 注册计划任务 ===' -ForegroundColor Cyan

# ── 1) 9443 中转：开机就起，不用登录 ──────────────────────────────────────
if (Test-Path $mid) {
    schtasks /Delete /TN 'KuaimaiHTTPS' /F > $null 2>&1
    $a = New-ScheduledTaskAction -Execute $mid -Argument '--port 9443' `
            -WorkingDirectory (Join-Path $dir 'kuaimai_https')
    Register-ScheduledTask -TaskName 'KuaimaiHTTPS' -Action $a `
        -Trigger (New-ScheduledTaskTrigger -AtStartup) -Principal $sys `
        -Settings $setInf -Force | Out-Null
    Write-Host '  [OK] KuaimaiHTTPS      开机(SYSTEM·无需登录) → km_https --port 9443' -ForegroundColor Green
} else {
    Write-Host "  [跳过] 没找到 $mid" -ForegroundColor DarkGray
}

# ── 2) frpc：同样开机就起 ────────────────────────────────────────────────
if ((Test-Path $frpc) -and (Test-Path $fcfg)) {
    schtasks /Delete /TN 'KuaimaiFrpc' /F > $null 2>&1
    $b = New-ScheduledTaskAction -Execute $frpc -Argument ('-c "' + $fcfg + '"') `
            -WorkingDirectory (Join-Path $dir 'frp')
    Register-ScheduledTask -TaskName 'KuaimaiFrpc' -Action $b `
        -Trigger (New-ScheduledTaskTrigger -AtStartup) -Principal $sys `
        -Settings $setInf -Force | Out-Null
    Write-Host '  [OK] KuaimaiFrpc       开机(SYSTEM·无需登录) → frpc' -ForegroundColor Green
} else {
    Write-Host '  [跳过] 没有 frp\frpc.toml（没配隧道就不需要）' -ForegroundColor DarkGray
}

# ── 3) 主程序：登录后起（它要桌面）──────────────────────────────────────
if (Test-Path $app) {
    $me = "$env:USERDOMAIN\$env:USERNAME"
    $usr = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
    $setApp = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
                -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
    schtasks /Delete /TN 'KuaimaiScan App' /F > $null 2>&1
    $c = New-ScheduledTaskAction -Execute $app -WorkingDirectory $dir
    Register-ScheduledTask -TaskName 'KuaimaiScan App' -Action $c `
        -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $me) -Principal $usr `
        -Settings $setApp -Force | Out-Null
    Write-Host "  [OK] KuaimaiScan App   登录($me) → 快麦扫码查询.exe" -ForegroundColor Green
} else {
    Write-Host "  [跳过] 没找到 $app" -ForegroundColor DarkGray
}

# ── 4) 看门狗：每 3 分钟巡检一次，谁挂了拉谁 ──────────────────────────────
if (Test-Path $dog) {
    schtasks /Delete /TN 'KuaimaiWatchdog' /F > $null 2>&1
    $d = New-ScheduledTaskAction -Execute 'powershell.exe' `
            -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $dog + '"')
    $t = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
            -RepetitionInterval (New-TimeSpan -Minutes 3)
    Register-ScheduledTask -TaskName 'KuaimaiWatchdog' -Action $d -Trigger $t `
        -Principal $sys -Settings $setInf -Force | Out-Null
    Write-Host '  [OK] KuaimaiWatchdog    每 3 分钟巡检(SYSTEM) → 看门狗.ps1' -ForegroundColor Green
} else {
    Write-Host "  [跳过] 没找到 $dog" -ForegroundColor DarkGray
}

# 老的"登录才起"的任务清掉，避免重复启动
foreach ($old in @('KuaimaiScan 启动', 'KuaimaiFrpc-旧')) {
    schtasks /Delete /TN $old /F > $null 2>&1
}
Write-Host ''
Write-Host '=== 注册完成，当前状态 ===' -ForegroundColor Cyan
Get-ScheduledTask -TaskName 'KuaimaiHTTPS','KuaimaiFrpc','KuaimaiScan App','KuaimaiWatchdog' `
    -ErrorAction SilentlyContinue | Select-Object TaskName, State | Format-Table -AutoSize

Write-Host '提示：' -ForegroundColor Yellow
Write-Host '  · 9443 中转 / frp：重启后**不需要任何人登录**就会自己起来' -ForegroundColor Gray
Write-Host '  · 主程序：要驱动 Edge 抓数据，必须在登录后的桌面里跑' -ForegroundColor Gray
Write-Host '  · 想让主程序也"重启就自动恢复"，请开启 Windows 自动登录（见「开启自动登录.cmd」）' -ForegroundColor Gray
Write-Host ''
