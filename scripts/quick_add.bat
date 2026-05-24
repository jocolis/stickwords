@echo off
cd /d "%~dp0\.."

where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw "%cd%\scripts\quick_add.py" %*
) else (
    python "%cd%\scripts\quick_add.py" %*
)
