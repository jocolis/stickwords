# Create a desktop shortcut for StickWords Quick Add and bind Ctrl+Alt+W.

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$targetPath = Join-Path $projectRoot "scripts\quick_add.bat"
$shortcutPath = [Environment]::GetFolderPath("Desktop") + "\StickWords Quick Add.lnk"

if (-not (Test-Path $targetPath)) {
    Write-Host "Missing $targetPath" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "Quickly add a word to StickWords"
$shortcut.WindowStyle = 7
$shortcut.Hotkey = "Ctrl+Alt+W"
$shortcut.Save()

Write-Host "Created: $shortcutPath" -ForegroundColor Green
Write-Host "Hotkey: Ctrl+Alt+W" -ForegroundColor Green
Read-Host "Press Enter to exit"
