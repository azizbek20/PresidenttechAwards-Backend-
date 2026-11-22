@echo off
echo Server jarayonlari to'xtatilmoqda...
wmic process where "commandline like '%%uvicorn%%'" call terminate >nul 2>&1
echo Barcha jarayonlar to'xtatildi!
pause
