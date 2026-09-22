# Read the login-window title of the frozen exe (embeds APP_VER) and clean up.
$ErrorActionPreference = "SilentlyContinue"
$src = "C:\Users\Kerwin\Desktop\发布\_build_v124\dist\快麦扫码查询.exe"
$smoke = "$env:TEMP\km_smoke_v124c"

# kill only smoke processes whose path is inside the smoke dir
Get-Process -Name "快麦扫码查询" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$env:TEMP\km_smoke_*" } | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 3
Remove-Item -Recurse -Force $smoke -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $smoke | Out-Null
Copy-Item $src "$smoke\快麦扫码查询.exe"

Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
  delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public static string Titles(uint target) {
    var sb = new StringBuilder();
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p); if (p == target) { var s = new StringBuilder(512); GetWindowTextW(h, s, 512); if (s.Length > 0) sb.Append(s.ToString()).Append(" | "); } return true; }, IntPtr.Zero);
    return sb.ToString();
  }
}
"@

$p = Start-Process -FilePath "$smoke\快麦扫码查询.exe" -WorkingDirectory $smoke -PassThru
Start-Sleep -Seconds 15
$proc = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
"PID=$($p.Id) alive=$($null -ne $proc) MainWindowTitle=[$($proc.MainWindowTitle)]"
"EnumWindows titles for PID $($p.Id) = [$( [W]::Titles([uint32]$p.Id) )]"
"--- files next to exe ---"
Get-ChildItem $smoke -Force | Select-Object Name | Format-Table -AutoSize

# clean up: kill parent + children belonging to the smoke dir
Get-Process -Name "快麦扫码查询" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$env:TEMP\km_smoke_*" } | ForEach-Object { "killing $($_.Id) $($_.Path)"; Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 2
"remaining smoke procs = $((Get-Process -Name '快麦扫码查询' -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$env:TEMP\km_smoke_*" } | Measure-Object).Count)"
$flag = "$env:LOCALAPPDATA\KuaimaiScan\auto_print_pause.flag"
"FLAG: exists=$(Test-Path $flag) sha=$((Get-FileHash $flag -Algorithm SHA256).Hash)"
