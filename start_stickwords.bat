@echo off
setlocal
cd /d "%~dp0"
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 1; Start-Process 'http://localhost:8000/admin'"
python app.py --host 0.0.0.0 --port 8000 --data-dir data
endlocal
