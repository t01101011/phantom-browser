$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$release = Join-Path $repo "apps/desktop/release"
$unpacked = Join-Path $release "win-unpacked"
$appExe = Join-Path $unpacked "Phantom Browser.exe"
$asar = Join-Path $unpacked "resources/app.asar"
$companion = Join-Path $unpacked "resources/companion/manifest.json"
$nativeRoot = Join-Path $unpacked "resources/app.asar.unpacked/node_modules/better-sqlite3"
$artifactDir = Join-Path $repo "artifacts/windows-smoke"
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null

$required = @($appExe, $asar, $companion, $nativeRoot)
foreach ($path in $required) {
  if (-not (Test-Path $path)) { throw "Missing packaged runtime path: $path" }
}

# A configured builder icon is not enough: signAndEditExecutable can be disabled,
# leaving Electron's default icon embedded in the actual PE. Extract the icon from
# the packaged EXE and compare its pixels with the canonical generated icon.
Add-Type -AssemblyName System.Drawing
$expectedIcon = Join-Path $repo "build/icon.ico"
if (-not (Test-Path $expectedIcon)) { throw "Missing canonical Windows icon: $expectedIcon" }

$embedded = [System.Drawing.Icon]::ExtractAssociatedIcon($appExe)
if (-not $embedded) { throw "Phantom Browser.exe has no associated icon" }
$expected = New-Object System.Drawing.Icon($expectedIcon, 32, 32)
$embeddedBitmap = $embedded.ToBitmap()
$expectedBitmap = $expected.ToBitmap()

try {
  if ($embeddedBitmap.Width -ne $expectedBitmap.Width -or $embeddedBitmap.Height -ne $expectedBitmap.Height) {
    throw "Embedded EXE icon dimensions differ from the canonical icon"
  }
  for ($y = 0; $y -lt $embeddedBitmap.Height; $y++) {
    for ($x = 0; $x -lt $embeddedBitmap.Width; $x++) {
      if ($embeddedBitmap.GetPixel($x, $y).ToArgb() -ne $expectedBitmap.GetPixel($x, $y).ToArgb()) {
        throw "Phantom Browser.exe does not embed the canonical product icon"
      }
    }
  }
} finally {
  $embeddedBitmap.Dispose()
  $expectedBitmap.Dispose()
  $embedded.Dispose()
  $expected.Dispose()
}

$native = Get-ChildItem $nativeRoot -Recurse -Filter "better_sqlite3.node" | Select-Object -First 1
if (-not $native) { throw "better_sqlite3.node was not unpacked" }

$installer = Get-ChildItem $release -Filter "Phantom Browser-win-x64.exe" | Select-Object -First 1
if (-not $installer) { throw "NSIS installer was not produced" }

$files = @($appExe, $asar, $companion, $native.FullName, $installer.FullName)
$hashes = foreach ($file in $files) {
  $item = Get-Item $file
  $hash = Get-FileHash $file -Algorithm SHA256
  [pscustomobject]@{
    path = $item.FullName.Substring($repo.Length + 1)
    bytes = $item.Length
    sha256 = $hash.Hash.ToLowerInvariant()
  }
}

$summary = [ordered]@{
  platform = [System.Environment]::OSVersion.VersionString
  app_executable = $appExe.Substring($repo.Length + 1)
  installer = $installer.FullName.Substring($repo.Length + 1)
  native_module = $native.FullName.Substring($repo.Length + 1)
  files = $hashes
}
$summary | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $artifactDir "package.json") -Encoding utf8
$summary | ConvertTo-Json -Depth 5
