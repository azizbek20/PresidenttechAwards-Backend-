@echo off
echo Server va Celery jarayonlari to'xtatilmoqda...
wmic process where "commandline like '%%uvicorn%%'" call terminate >nul 2>&1
wmic process where "commandline like '%%celery%%'" call terminate >nul 2>&1
echo Barcha jarayonlar to'xtatildi!
pause
