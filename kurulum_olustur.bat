@echo off
rem Kurulum dosyasini (dist\Tuckly-Setup-<surum>.exe) uretir. Gereksinim: Inno Setup 6 (ISCC.exe).
cd /d "%~dp0"
if not exist "dist\Tuckly\Tuckly.exe" call exe_olustur.bat
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 bulunamadi. https://jrsoftware.org/isinfo.php adresinden kurun.
  pause
  exit /b 1
)
"%ISCC%" installer\tuckly.iss
pause
