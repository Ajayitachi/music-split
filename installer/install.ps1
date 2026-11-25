# Installs Multi Headphones for the current user (no admin needed):
# copies the app to %LOCALAPPDATA%\Programs\Multi Headphones, adds Start Menu + Desktop shortcuts
# and an entry in Settings > Apps so it can be uninstalled normally.
$ErrorActionPreference = "Stop"
$name = "Multi Headphones"
$src = $PSScriptRoot
$dest = Join-Path $env:LOCALAPPDATA "Programs\$name"
$exe = Join-Path $dest "MultiHeadphones.exe"

if (-not (Test-Path (Join-Path $src "MultiHeadphones.exe"))) { throw "MultiHeadphones.exe not found next to the installer." }

Get-Process MultiHeadphones -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item (Join-Path $src "*") $dest -Recurse -Force
Remove-Item (Join-Path $dest "Install.bat"), (Join-Path $dest "install.ps1") -ErrorAction SilentlyContinue

$shell = New-Object -ComObject WScript.Shell
$links = @(
    (Join-Path ([Environment]::GetFolderPath("Programs")) "$name.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "$name.lnk")
)
foreach ($l in $links) {
    $s = $shell.CreateShortcut($l)
    $s.TargetPath = $exe
    $s.WorkingDirectory = $dest
    $s.IconLocation = "$exe,0"
    $s.Description = "Play a movie's sound on several headphones at once"
    $s.Save()
}

$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MultiHeadphones"
New-Item -Force $key | Out-Null
$un = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$dest\uninstall.ps1`""
Set-ItemProperty $key DisplayName $name
Set-ItemProperty $key DisplayVersion "1.0.0"
Set-ItemProperty $key Publisher "Ajayitachi"
Set-ItemProperty $key DisplayIcon "$exe,0"
Set-ItemProperty $key InstallLocation $dest
Set-ItemProperty $key UninstallString $un
Set-ItemProperty $key NoModify 1 -Type DWord
Set-ItemProperty $key NoRepair 1 -Type DWord

Write-Host "Installed to $dest"
Start-Process $exe
