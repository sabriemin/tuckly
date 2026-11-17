@echo off
rem Tuckly.exe dosyasini dist\Tuckly klasorune derler.
cd /d "%~dp0"
python -m pip install --upgrade PySide6 pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name Tuckly ^
  --icon assets\tuckly.ico --version-file tools\version_info.txt ^
  --add-data "tuckly\assets;assets" run.py
echo.
echo Hazir: dist\Tuckly\Tuckly.exe
pause
