@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   🔥 FireSuppressor – Automated Windows Setup 🔥
echo ============================================================
echo.

:: 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

:: 2. Create Virtual Environment
if not exist .venv (
    echo [1/4] Creating virtual environment (.venv)...
    python -m venv .venv
) else (
    echo [1/4] Virtual environment already exists.
)

:: 3. Install Dependencies
echo [2/4] Installing dependencies...
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 4. Download Models
echo [3/4] Downloading AI model weights...
python models/download_models.py --build-only

:: 5. Finalize
echo [4/4] Setup complete!
echo.
echo To start the backend:
echo   .venv\Scripts\activate
echo   python main.py --demo
echo.
echo To start the dashboard (frontend):
echo   cd frontend
echo   npm install
echo   npm start
echo.
pause
