# ============================================================================
#  开启 Windows 自动登录 —— 让主程序在重启后也能自动恢复（需要管理员）
#
#  ⚠ 会把密码明文写进本机注册表 HKLM\...\Winlogon\DefaultPassword
#     这台电脑只有你自己用、且必须无人值守才建议开。
#     想关掉：运行「关闭自动登录.cmd」，或把 AutoAdminLogon 改成 0。
# ============================================================================
$ErrorActionPreference = 'Stop'
$key = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$p  = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host '需要管理员权限。' -ForegroundColor Yellow
    exit 1
}

Write-Host ''
Write-Host '=== 开启自动登录 ===' -ForegroundColor Cyan
Write-Host "当前用户：$env:USERNAME   计算机名：$env:COMPUTERNAME"
Write-Host ''
$pw = Read-Host '请输入这个 Windows 账号的密码（输入时不显示）' -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw))
if ([string]::IsNullOrEmpty($plain)) {
    Write-Host '密码为空，取消。' -ForegroundColor Yellow
    exit 1
}

# 先备份原值，方便回退
$bak = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'autologon-backup.txt'
try {
    $old = Get-ItemProperty -Path $key
    @(
        'AutoAdminLogon=' + $old.AutoAdminLogon
        'DefaultUserName=' + $old.DefaultUserName
        'DefaultDomainName=' + $old.DefaultDomainName
    ) | Set-Content -Path $bak -Encoding utf8
    Write-Host "  原设置已备份到：$bak" -ForegroundColor DarkGray
} catch { }

Set-ItemProperty -Path $key -Name 'AutoAdminLogon'   -Value '1'
Set-ItemProperty -Path $key -Name 'DefaultUserName'  -Value $env:USERNAME
Set-ItemProperty -Path $key -Name 'DefaultDomainName' -Value $env:COMPUTERNAME
Set-ItemProperty -Path $key -Name 'DefaultPassword'  -Value $plain
# Win10/11 还要把 DevicePasswordLessBuildVersion 关掉，否则走的是 PIN/无密码流程
$np = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device'
if (Test-Path $np) {
    Set-ItemProperty -Path $np -Name 'DevicePasswordLessBuildVersion' -Value 0 -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host '  [OK] 已开启自动登录' -ForegroundColor Green
Write-Host '       下次重启会直接进桌面 → 计划任务随即拉起主程序 + 9443 中转' -ForegroundColor Gray
Write-Host '       想关掉：把注册表 AutoAdminLogon 改成 0（或运行 关闭自动登录.cmd）' -ForegroundColor Gray
Write-Host ''
