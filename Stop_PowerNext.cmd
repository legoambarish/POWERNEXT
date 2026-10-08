@echo off
setlocal
cd /d "%~dp0"
"%~dp0runtime\python.exe" -m powernext_app.stop %*
if errorlevel 1 pause
