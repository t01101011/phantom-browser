$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$appExe = Join-Path $repo "apps/desktop/release/win-unpacked/Phantom Research.exe"
$artifactDir = Join-Path $repo "artifacts/windows-smoke"
$stdout = Join-Path $artifactDir "desktop.stdout.log"
$stderr = Join-Path $artifactDir "desktop.stderr.log"
$userData = Join-Path $artifactDir "user-data"
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
New-Item -ItemType Directory -Force -Path $userData | Out-Null

if (-not (Test-Path $appExe)) { throw "Packaged desktop missing: $appExe" }

$env:MULTIZEN_NO_TELEMETRY = "1"
$proc = Start-Process -FilePath $appExe `
  -ArgumentList @("--user-data-dir=$userData") `
  -PassThru `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr

try {
  $deadline = (Get-Date).AddSeconds(20)
  $ready = $false
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    $proc.Refresh()
    if ($proc.HasExited) {
      $err = if (Test-Path $stderr) { Get-Content $stderr -Raw } else { "" }
      throw "Packaged desktop exited during cold start with code $($proc.ExitCode): $err"
    }
    if ($proc.MainWindowHandle -ne 0) {
      $ready = $true
      break
    }
  }
  if (-not $ready) { throw "Packaged desktop did not create a main window within 20 seconds" }

  $settingsPath = Join-Path $userData "settings.json"
  $tokenPath = Join-Path $userData "mcp-token"
  $deadline = (Get-Date).AddSeconds(10)
  while ((Get-Date) -lt $deadline -and -not (Test-Path $tokenPath)) {
    Start-Sleep -Milliseconds 300
  }
  if (-not (Test-Path $tokenPath)) { throw "Desktop did not initialize its local MCP token" }

  $result = [ordered]@{
    pid = $proc.Id
    main_window = $proc.MainWindowHandle.ToInt64()
    mcp_token_created = $true
    settings_created = (Test-Path $settingsPath)
    user_data = $userData.Substring($repo.Length + 1)
  }
  $result | ConvertTo-Json | Set-Content (Join-Path $artifactDir "desktop.json") -Encoding utf8
  $result | ConvertTo-Json
}
finally {
  if (-not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
    $proc.WaitForExit(10000) | Out-Null
  }
  Start-Sleep -Seconds 1
  if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
    throw "Desktop process survived forced shutdown"
  }
}
