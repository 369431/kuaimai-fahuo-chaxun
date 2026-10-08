# ============================================================================
#  看门狗 —— 每 3 分钟巡检一次，谁挂了就拉谁（SYSTEM 身份跑，不需要有人登录）
#
#  它管三样：
#    1) 9443 没在监听      → 拉起 km_https.exe --port 9443
#    2) frpc 进程不在      → 拉起 frpc -c frpc.toml（如果配了）
#    3) 主程序不在         → 用计划任务「KuaimaiScan App」以用户身份启动
#                            （SYSTEM 不能直接在用户桌面里开 GUI，必须借道计划任务）
#
#  日志：同目录 watchdog.log（只留最近 500 行）
# ============================================================================
$ErrorActionPreference = 'SilentlyContinue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $dir 'watchdog.log'

function Say($msg) {
    try {
        "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" |
            Out-File -FilePath $log -Append -Encoding utf8
    } catch { }
}

$did = @()

# ── 1) 9443 中转 ─────────────────────────────────────────────────────────
$mid = Join-Path $dir 'kuaimai_https\km_https.exe'
$listen = Get-NetTCPConnection -LocalPort 9443 -State Listen -ErrorAction SilentlyContinue
if (-not $listen -and (Test-Path $mid)) {
    Start-Process -FilePath $mid -ArgumentList '--port', '9443' `
        -WorkingDirectory (Join-Path $dir 'kuaimai_https') -WindowStyle Hidden
    $did += '9443中转(没监听→已拉起)'
    Say '9443 没在监听 → 拉起 km_https'
}

# 中转进程还在、但端口没监听（卡死）→ 杀掉重来
if ($listen -and (Test-Path $mid)) {
    $mp = Get-Process -Name 'km_https' -ErrorAction SilentlyContinue
    if ($mp -and $mp.Count -gt 3) {
        # 正常应该是 1~2 个（父+子），多出来的是僵尸
        $mp | Sort-Object StartTime | Select-Object -Skip 2 | ForEach-Object { $_.Kill() }
        $did += '9443中转(清了多余进程)'
        Say 'km_https 进程数异常 → 清理僵尸'
    }
}

# ── 2) frpc ──────────────────────────────────────────────────────────────
$frpc = Join-Path $dir 'frp\frpc.exe'
$fcfg = Join-Path $dir 'frp\frpc.toml'
if ((Test-Path $frpc) -and (Test-Path $fcfg)) {
    if (-not (Get-Process -Name 'frpc' -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $frpc -ArgumentList '-c', ('"' + $fcfg + '"') `
            -WorkingDirectory (Join-Path $dir 'frp') -WindowStyle Hidden
        $did += 'frpc(不在→已拉起)'
        Say 'frpc 不在 → 拉起'
    }
}

# ── 3) 主程序（GUI，必须在用户会话里跑）──────────────────────────────────
$app = Join-Path $dir '快麦扫码查询.exe'
if ((Test-Path $app) -and -not (Get-Process -Name '快麦扫码查询' -ErrorAction SilentlyContinue)) {
    $t = Get-ScheduledTask -TaskName 'KuaimaiScan App' -ErrorAction SilentlyContinue
    if ($t) {
        Start-ScheduledTask -TaskName 'KuaimaiScan App'
        $did += '主程序(不在→借计划任务以用户身份启动)'
        Say '主程序不在 → 通过计划任务启动'
    } else {
        Say '主程序不在，但没找到计划任务 KuaimaiScan App（可能还没登录过）'
    }
}

# ── 日志裁剪 ─────────────────────────────────────────────────────────────
if (Test-Path $log) {
    $lines = @(Get-Content $log -ErrorAction SilentlyContinue)
    if ($lines.Count -gt 500) {
        $lines | Select-Object -Last 500 | Set-Content -FilePath $log -Encoding utf8
    }
}

# 有动作才输出（平时静默，不刷屏）
if ($did.Count -gt 0) { Write-Host ('看门狗处理: ' + ($did -join ' / ')) }
