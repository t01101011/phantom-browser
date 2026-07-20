param(
  [Parameter(Mandatory=$true)][string]$BundleRoot,
  [switch]$SkipBrowserSession,
  [switch]$SidecarOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path $BundleRoot).Path
$sidecar = Join-Path $root 'phantom-sidecar\phantom-sidecar.exe'
$app = Join-Path $root 'Phantom Browser.exe'
$webview = Get-ItemPropertyValue -Path 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F1E7A8B0-8E8A-4A40-8D0F-0B2D0B9A3E7B}' -Name pv -ErrorAction SilentlyContinue
if (!(Test-Path $sidecar)) { throw "Missing packaged sidecar: $sidecar" }
if (!(Test-Path (Join-Path $root 'phantom-sidecar\_internal\camoufox\camoufox.exe'))) { throw 'Missing Camoufox browser asset' }
if (!(Test-Path $app)) { throw "Missing desktop executable: $app" }
if (!$webview -and !(Test-Path (Join-Path $root 'WebView2Loader.dll'))) { Write-Warning 'WebView2 runtime registry key not found; loader may be embedded statically' }

$data = Join-Path $env:RUNNER_TEMP ("phantom-smoke-" + [guid]::NewGuid())
$port = 52100 + (Get-Random -Maximum 1000)
$env:PHANTOM_DATA_DIR = $data
$stdoutLog = Join-Path $data 'sidecar.stdout.log'
$stderrLog = Join-Path $data 'sidecar.stderr.log'
New-Item -ItemType Directory -Force $data | Out-Null
$process = Start-Process -FilePath $sidecar -ArgumentList @('serve','--host','127.0.0.1','--port',"$port",'--log-level','warning') -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
try {
  $tokenPath = Join-Path $data 'runtime\.api_token'; $deadline = (Get-Date).AddSeconds(45); $token = $null; $ready = $null; $lastReadyError = 'not attempted'
  do {
    if ($process.HasExited) { throw "Sidecar exited early: $($process.ExitCode)" }
    if (Test-Path $tokenPath) { $token = (Get-Content -Raw $tokenPath).Trim() }
    if ($token) {
      try {
        $ready = Invoke-RestMethod "http://127.0.0.1:$port/readyz" -Headers @{Authorization="Bearer $token"}
        $lastReadyError = "HTTP success, status=$($ready.status), db=$($ready.db)"
        if ($ready.status -eq 'ready') { break }
      } catch {
        $lastReadyError = $_.Exception.Message
      }
    } else {
      $lastReadyError = "token missing at $tokenPath"
    }
    Start-Sleep -Milliseconds 200
  } while ((Get-Date) -lt $deadline)
  if (!$token -or !$ready -or $ready.status -ne 'ready') {
    $health = try { (Invoke-RestMethod "http://127.0.0.1:$port/healthz" | ConvertTo-Json -Compress) } catch { "error: $($_.Exception.Message)" }
    $stdout = if (Test-Path $stdoutLog) { (Get-Content -Raw $stdoutLog).Trim() } else { '<missing>' }
    $stderr = if (Test-Path $stderrLog) { (Get-Content -Raw $stderrLog).Trim() } else { '<missing>' }
    throw "Authenticated /readyz timeout; lastReadyError=$lastReadyError; healthz=$health; sidecarPid=$($process.Id); tokenExists=$(Test-Path $tokenPath); stdout=$stdout; stderr=$stderr"
  }
  $headers = @{Authorization="Bearer $token"; 'Content-Type'='application/json'}
  $body = @{name='windows-ci-smoke'; platform_tag='custom'; proxy_host=''; proxy_port=0} | ConvertTo-Json
  $profile = Invoke-RestMethod "http://127.0.0.1:$port/v1/profiles" -Method Post -Headers $headers -Body $body
  $profiles = Invoke-RestMethod "http://127.0.0.1:$port/v1/profiles" -Headers $headers
  if (!($profiles.profiles.id -contains $profile.id)) { throw 'Profile CRUD smoke failed' }
  if (!$SkipBrowserSession) {
    $instantBody = @{profile_id=$profile.id; ttl_seconds=30} | ConvertTo-Json
    $instant = Invoke-RestMethod "http://127.0.0.1:$port/v1/sessions/instant" -Method Post -Headers $headers -Body $instantBody
    if (!$instant.session.id) { throw 'Instant session did not return an id' }
    Invoke-RestMethod "http://127.0.0.1:$port/v1/sessions/$($instant.session.id)" -Method Delete -Headers $headers | Out-Null
  }
  Write-Host 'PASS: packaged Windows health/profile/instant smoke'
} finally {
  if (!$process.HasExited) { & taskkill.exe /PID $process.Id /T /F | Out-Null; $process.WaitForExit(15000) | Out-Null }
  Start-Sleep -Milliseconds 500
  $left = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) }
  if ($left) { $left | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; throw "Packaged process leak: $($left.Name -join ', ')" }
  Remove-Item $data -Recurse -Force -ErrorAction SilentlyContinue
}
if ($SidecarOnly) { exit 0 }

# Cold-start the actual Tauri desktop and require its packaged child to survive.
$data = Join-Path $env:RUNNER_TEMP ("phantom-desktop-smoke-" + [guid]::NewGuid())
$env:PHANTOM_DATA_DIR = $data
$desktop = Start-Process -FilePath $app -WorkingDirectory $root -PassThru
try {
  $deadline = (Get-Date).AddSeconds(45); $child = $null
  do {
    if ($desktop.HasExited) { throw "Desktop exited during cold start: $($desktop.ExitCode)" }
    $child = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $desktop.Id -and $_.Name -eq 'phantom-sidecar.exe' }
    if ($child -and (Test-Path (Join-Path $data 'runtime\.api_token'))) { break }
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $deadline)
  if (!$child) { throw 'Desktop did not start packaged sidecar' }
} finally {
  if (!$desktop.HasExited) { & taskkill.exe /PID $desktop.Id /T /F | Out-Null; $desktop.WaitForExit(15000) | Out-Null }
  Start-Sleep -Seconds 1
  $left = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) }
  if ($left) { throw "Desktop process-tree cleanup failed: $($left.Name -join ', ')" }
  Remove-Item $data -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host 'PASS: desktop cold start and process-tree cleanup'
