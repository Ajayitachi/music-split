# Removes Multi Headphones (keeps your saved settings in %APPDATA%\Multi Headphones).
$name = "Multi Headphones"
$dest = Join-Path $env:LOCALAPPDATA "Programs\$name"
Get-Process MultiHeadphones -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
Remove-Item (Join-Path ([Environment]::GetFolderPath("Programs")) "$name.lnk") -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "$name.lnk") -ErrorAction SilentlyContinue
Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MultiHeadphones" -Recurse -ErrorAction SilentlyContinue
# the script lives inside the folder it deletes, so finish the delete from a separate process
Start-Process cmd.exe -ArgumentList "/c timeout /t 2 >nul & rmdir /s /q `"$dest`"" -WindowStyle Hidden
