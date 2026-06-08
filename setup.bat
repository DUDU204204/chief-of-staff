@echo off
REM Chief of Staff — first-time setup (Windows)
REM Run from inside the repo: setup.bat

setlocal

echo.
echo  Chief of Staff - setup
echo.

REM 1. Python version check
where python >nul 2>nul
if errorlevel 1 (
  echo [X] python not found. Install Python 3.10+ from python.org first.
  exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VERSION=%%i
echo [v] Python %PY_VERSION%

REM 2. Create data directory
if not exist "data" mkdir data
echo [v] data\ dir ready

REM 3. Run discovery
echo.
echo  Running auto-discovery...
python discover.py
echo.

REM 4. Tell user what's next
echo ---------------------------------------------
echo  Setup complete!
echo.
echo  Next steps:
echo    1. Start the server:
echo         python server.py
echo.
echo    2. Open the office in your browser:
echo         http://127.0.0.1:17090
echo.
echo    3. (Optional) Register your own systems:
echo         copy systems.json.example systems.json
echo         REM edit systems.json in any editor
echo         python discover.py
echo ---------------------------------------------

endlocal
