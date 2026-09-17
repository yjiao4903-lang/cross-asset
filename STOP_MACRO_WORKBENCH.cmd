@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\stop.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Macro Workbench could not be stopped safely. See launcher\logs\launcher.log for details.
  pause
)
exit /b %EXIT_CODE%