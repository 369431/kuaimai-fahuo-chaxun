$ErrorActionPreference = 'SilentlyContinue'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$frpc = Join-Path $dir 'frp\frpc.exe'
$cfg  = Join-Path $dir 'frp\frpc.toml'
$start = Join-Path $dir '启动全部.ps1'
cmd /c 'schtasks /Delete /TN "KuaimaiScan 启动" /F >nul 2>&1' | Out-Null
$act1 = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $start + '"')
$set1 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'KuaimaiScan 启动' -Action $act1 -Trigger (New-ScheduledTaskTrigger -AtLogOn) -Settings $set1 -Force | Out-Null
Start-ScheduledTask -TaskName 'KuaimaiScan 启动'
if ((Test-Path $frpc) -and (Test-Path $cfg)) {
    cmd /c "schtasks /Delete /TN KuaimaiFrpc /F >nul 2>&1" | Out-Null
    $act2 = New-ScheduledTaskAction -Execute $frpc -Argument ('-c "' + $cfg + '"') -WorkingDirectory (Join-Path $dir 'frp')
    $set2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName 'KuaimaiFrpc' -Action $act2 -Trigger (New-ScheduledTaskTrigger -AtLogOn) -Settings $set2 -Force | Out-Null
    Start-ScheduledTask -TaskName 'KuaimaiFrpc'
}
Start-Sleep -Seconds 5
Get-ScheduledTask -TaskName 'KuaimaiScan 启动','KuaimaiFrpc' | Select-Object TaskName, State | Format-Table -AutoSize
