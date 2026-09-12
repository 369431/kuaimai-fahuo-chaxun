# lego_run.ps1 - call lego using the local credential files (lego v5 CLI).
# Values go only into the child process environment: never printed, never on a command line.
# Usage: powershell -File .\lego_run.ps1 issue|renew|status
#   issue / renew : both run "lego run"; lego itself decides whether renewal is due.
#   --dns.resolvers: 1.1.1.1:53 is unreachable from this network (UDP 53 blocked),
#                    so pin Aliyun public DNS for the propagation checks.
param([Parameter(Position = 0)][string]$Action = "status")

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Lego = Join-Path $Root 'lego.exe'
$LegoPath = Join-Path $Root 'lego'
$AkFile = Join-Path $Root 'aliyun\access_key.txt'
$SkFile = Join-Path $Root 'aliyun\access_key_secret.txt'
$Domain = 'shsp.pw'
$Resolvers = @('--dns.resolvers', '223.5.5.5:53', '--dns.resolvers', '223.6.6.6:53')

function Set-EnvFromFile([string]$EnvName, [string]$File, [string]$Label) {
  if (-not (Test-Path $File)) { throw "$Label file missing: $File" }
  $v = (Get-Content $File -Raw).Trim()
  if (-not $v) { throw "$Label file is empty: $File" }
  if ($v -match 'PASTE_') { throw "$Label not filled in yet (still a placeholder): $File" }
  Set-Item -Path ('Env:' + $EnvName) -Value $v
}

$LegoArgs = $null
switch ($Action) {
  'status' {
    & $Lego certificates list --path $LegoPath
    exit $LASTEXITCODE
  }
  'issue' {
    $LegoArgs = @('run', '--path', $LegoPath, '--accept-tos', '--dns', 'alidns',
                  '--domains', $Domain, '--key-type', 'RSA2048', '--renew-days', '30') + $Resolvers
  }
  'renew' {
    $LegoArgs = @('run', '--path', $LegoPath, '--accept-tos', '--dns', 'alidns',
                  '--domains', $Domain, '--key-type', 'RSA2048', '--renew-days', '30') + $Resolvers
  }
  default { throw "Unknown action '$Action' (use: issue / renew / status)" }
}

Set-EnvFromFile 'ALICLOUD_ACCESS_KEY' $AkFile 'AccessKey ID'
Set-EnvFromFile 'ALICLOUD_SECRET_KEY' $SkFile 'AccessKey Secret'
try {
  & $Lego @LegoArgs
  exit $LASTEXITCODE
} finally {
  Remove-Item Env:\ALICLOUD_ACCESS_KEY -ErrorAction SilentlyContinue
  Remove-Item Env:\ALICLOUD_SECRET_KEY -ErrorAction SilentlyContinue
}
