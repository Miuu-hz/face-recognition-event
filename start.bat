@echo off
REM Face Recognition Event - Windows Startup Script
REM For Windows users who cannot use bash scripts

echo ======================================
echo Face Recognition Event - Windows
echo ======================================
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo Error: Virtual environment not found!
    echo Please create it first:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements-local.txt
    pause
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if Flask is installed
python -c "import flask" 2>nul
if errorlevel 1 (
    echo Error: Flask is not installed!
    echo Please run: pip install -r requirements-local.txt
    pause
    exit /b 1
)

REM Check if localtunnel is installed
where lt >nul 2>nul
if errorlevel 1 (
    echo Warning: Localtunnel is not installed!
    echo Installing localtunnel...
    npm install -g localtunnel
    if errorlevel 1 (
        echo Error: Failed to install localtunnel!
        echo Please install Node.js first
        pause
        exit /b 1
    )
)

REM Set port
set PORT=10000

echo.
echo ======================================
echo Starting Flask server...
echo ======================================
echo.

REM Start Flask in background
start /B python app.py > flask.log 2>&1

REM Wait for Flask to start
timeout /t 3 /nobreak >nul

echo Flask server started on port %PORT%
echo.

echo ======================================
echo Starting Localtunnel...
echo ======================================
echo.

REM Start Localtunnel in background
start /B lt --port %PORT% > lt.log 2>&1

REM Wait for localtunnel
timeout /t 3 /nobreak >nul

echo.
echo ======================================
echo System is ready!
echo ======================================
echo.
echo Access your application at:
echo.
echo Local:  http://localhost:%PORT%
echo.
echo Check lt.log for the Public URL
type lt.log | findstr "https://"
echo.
echo ======================================
echo.
echo Logs:
echo   Flask:       type flask.log
echo   Localtunnel: type lt.log
echo.
echo Press Ctrl+C to stop (you may need to close terminal)
echo.

REM Keep window open
pause
