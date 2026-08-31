@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
start "" /B python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
start "" /B python -m celery -A app.worker.celery_app worker --pool=solo --loglevel=info
