# 快麦扫码查询 —— 一键打安装包
#
#   PyInstaller 出主程序 → 摆好 staging → ISCC 出安装版 exe
#
# 用法（脚本自己定位路径，哪里跑都行）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1 -Version 1.25
#   ... -SkipFrp        # staging 里已有 frpc.exe 时跳过（省一次下载）
#   ... -SkipPack       # 只摆 staging、不跑 PyInstaller（复用上次的 exe，调 iss 时快）
#
# 产出：packaging\out\快麦扫码查询_安装版_v<版本>.exe
#
# 前置：Python + PyInstaller、Inno Setup 6（ISCC.exe）。
# 注意：frpc.exe 是第三方二进制（13 MB），不入库，首次跑由 download_frp.ps1 抓进 packaging\frp\。
#       主程序的 hiddenimports 在 快麦扫码查询.spec 里，别用 README 那条裸 --onefile 命令代替。
param(
    [string]$Version = "",
    [switch]$SkipFrp,
    [switch]$SkipPack
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Here = $PSScriptRoot
$Repo = Split-Path -Parent $Here
$Stage = Join-Path $Here 'staging'
$Out = Join-Path $Here 'out'
$Work = Join-Path $Here '_work'

function Say($m) { Write-Host $m }

# ── 0. 版本号：没传就从 desktop\kuaimai_client.py 的 APP_VER 读 ────────────────
if (-not $Version) {
    $clientPy = Join-Path $Repo 'desktop\kuaimai_client.py'
    $m = Select-String -Path $clientPy -Pattern 'APP_VER\s*=\s*"v([\d.]+)"'
    if (-not $m) { throw "读不到 APP_VER（$clientPy）→ 用 -Version 1.25 显式指定" }
    $Version = $m.Matches[0].Groups[1].Value
    Say "[0] 版本号取自 kuaimai_client.py → $Version"
} else {
    Say "[0] 版本号（命令行指定）→ $Version"
}

# ── 1. 找 ISCC.exe ─────────────────────────────────────────────────────────────
$isccCand = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe'
)
$iscc = $isccCand | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}
if (-not $iscc) { throw "找不到 ISCC.exe，请装 Inno Setup 6 或把它加进 PATH" }
Say "[1] ISCC = $iscc"

# ── 2. 重建 staging ────────────────────────────────────────────────────────────
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Stage, $Out | Out-Null
foreach ($f in Get-ChildItem (Join-Path $Here 'assets') -File) {
    Copy-Item $f.FullName (Join-Path $Stage $f.Name) -Force
}
Say "[2] assets → staging（$((Get-ChildItem (Join-Path $Here 'assets') -File).Count) 个文件）"

# ── 3. HTTPS 中转：仓库 https\ → staging\kuaimai_https ─────────────────────────
$mid = Join-Path $Stage 'kuaimai_https'
New-Item -ItemType Directory -Force -Path (Join-Path $mid 'static') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $mid 'lego\certificates') | Out-Null
Copy-Item (Join-Path $Repo 'https\km_https.py') $mid -Force
Copy-Item (Join-Path $Repo 'https\certinfo.py') $mid -Force
Copy-Item (Join-Path $Repo 'https\static\scan.js') (Join-Path $mid 'static') -Force
Copy-Item (Join-Path $Repo 'https\static\zxing.js') (Join-Path $mid 'static') -Force
Copy-Item (Join-Path $Here 'assets\把证书放这里.txt') (Join-Path $mid 'lego\certificates') -Force
# km_https.exe：从 km_https.py 打的单文件（BASE 取 sys.executable 所在目录 →
# 启动它就是 kuaimai_https\，static / lego 都在旁边）。没现成的就退回用 .py 跑。
$midExe = Join-Path $Repo 'https\km_https.exe'
if (Test-Path $midExe) { Copy-Item $midExe $mid -Force; Say "[3] kuaimai_https（含 km_https.exe）" }
else { Say "[3] kuaimai_https（⚠ 没有 km_https.exe，安装后会退回用 pythonw 跑 km_https.py）" }

# ── 4. frpc.exe（第三方二进制，不入库）────────────────────────────────────────
$frpDst = Join-Path $Stage 'frp'
New-Item -ItemType Directory -Force -Path $frpDst | Out-Null
$frpSrc = Join-Path $Here 'frp\frpc.exe'
if ((-not (Test-Path $frpSrc)) -and (-not $SkipFrp)) {
    Say "[4] 本地没有 frpc.exe → 调 download_frp.ps1"
    & (Join-Path $Here 'download_frp.ps1')
}
if (Test-Path $frpSrc) {
    Copy-Item $frpSrc $frpDst -Force
    Say "[4] frpc.exe → staging\frp\（$([math]::Round((Get-Item $frpSrc).Length/1MB,1)) MB）"
} else {
    throw "缺 frpc.exe：先跑 packaging\download_frp.ps1（或手工放到 packaging\frp\frpc.exe）"
}

# ── 5. PyInstaller 打主程序 ────────────────────────────────────────────────────
if ($SkipPack) {
    Say "[5] -SkipPack：跳过打包，沿用 staging 里现有的 exe"
    if (-not (Test-Path (Join-Path $Stage '快麦扫码查询.exe'))) { throw "staging 里没有 快麦扫码查询.exe，不能 -SkipPack" }
} else {
    Say "[5] PyInstaller 打包中…（约 15~60 秒）"
    $t0 = Get-Date
    # 原生命令往 stderr 写日志时，PS 5.1 会造 NativeCommandError；$ErrorActionPreference='Stop'
    # 会把它当致命错误直接终止（看着像 PyInstaller 失败，其实只是 INFO 行）→ 这里临时降级。
    $ea = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    python -m PyInstaller --noconfirm --distpath $Stage --workpath $Work `
        (Join-Path $Here '快麦扫码查询.spec') *> (Join-Path $Out 'pyinstaller.log')
    $packRc = $LASTEXITCODE
    $ErrorActionPreference = $ea
    if ($packRc -ne 0) { throw "PyInstaller 失败（退出码 $packRc）→ 看 out\pyinstaller.log" }
    $exe = Join-Path $Stage '快麦扫码查询.exe'
    if (-not (Test-Path $exe)) { throw "PyInstaller 跑完但没看到 $exe" }
    $span = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    Say ("[5] 主程序 = {0} MB（{1}s）" -f [math]::Round((Get-Item $exe).Length / 1MB, 2), $span)
}

# ── 6. ISCC 出安装包 ───────────────────────────────────────────────────────────
Say "[6] ISCC 编译安装包…"
$ea = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $iscc (Join-Path $Here '快麦扫码查询.iss') "/DMyAppVersion=$Version" | Out-Null
$isccRc = $LASTEXITCODE
$ErrorActionPreference = $ea
if ($isccRc -ne 0) { throw "ISCC 失败（退出码 $isccRc）" }
$setup = Join-Path $Out "快麦扫码查询_安装版_v$Version.exe"
if (-not (Test-Path $setup)) { throw "ISCC 跑完但没看到 $setup" }

$f = Get-Item $setup
Say ""
Say "==== 完成 ===="
Say ("安装包 : {0}" -f $f.FullName)
Say ("大小   : {0} MB" -f [math]::Round($f.Length / 1MB, 2))
Say ("版本   : {0}" -f $f.VersionInfo.ProductVersion)
Say ""
Say "下一步（把新版推给客户端）："
Say ("  1) python tools\_do_release_vXXX.py     # 参考 tools\_do_release_v125.py（发 Release + 更新 version.json）")
Say ("  2) 清 jsDelivr 缓存（客户端默认清单源，不清会继续返回旧版）：")
Say ("     https://purge.jsdelivr.net/gh/369431/kuaimai-fahuo-chaxun@main/version.json")
