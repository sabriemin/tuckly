@echo off
rem Derlenmis Tuckly.exe varsa onu, yoksa Python ile kaynak kodu baslatir.
cd /d "%~dp0"
if exist "dist\Tuckly\Tuckly.exe" (
  start "" "dist\Tuckly\Tuckly.exe"
) else (
  python -c "import PySide6" 2>nul || python -m pip install PySide6
  start "" pythonw "%~dp0run.py"
)
