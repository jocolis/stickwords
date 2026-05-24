$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$port = 8000

Set-Location $projectRoot

Write-Host "Checking for existing StickWords backend on port $port..."
$listeningPids = @()
netstat -ano | ForEach-Object {
    if ($_ -match "^\s*TCP\s+\S+:$port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
        $listeningPids += [int]$Matches[1]
    }
}

$listeningPids | Sort-Object -Unique | ForEach-Object {
    if ($_ -ne $PID) {
        Write-Host "Stopping old backend process PID $_..."
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
}

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoProfile",
    "-Command",
    "Start-Sleep -Seconds 1; Start-Process 'http://localhost:8000/admin'"
)

Write-Host "Starting StickWords backend on http://localhost:8000/admin"
python app.py --host 0.0.0.0 --port 8000 --data-dir data
