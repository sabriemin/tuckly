@echo off
rem Tuckly.exe dosyasini dist\Tuckly klasorune derler (tarif: tuckly.spec).
cd /d "%~dp0"
python -m pip install --upgrade -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean tuckly.spec
echo.
echo Hazir: dist\Tuckly\Tuckly.exe
pause
