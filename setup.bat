@echo off
REM setup.bat - התקנה ראשונה של "המשרד שלי" בווינדוס
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo המשרד שלי - התקנה
echo -------------------
python --version >nul 2>&1 || (echo [X] לא נמצא Python. התקן מ-python.org עם "Add Python to PATH" && exit /b 1)
for /f "tokens=*" %%v in ('python --version') do echo [V] %%v
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" || (echo [X] נדרש Python 3.10 ומעלה && exit /b 1)
where claude >nul 2>&1 && (echo [V] Claude Code נמצא) || (echo [!] claude לא ב-PATH - הגילוי יעבוד, כפתור "הפעל" לא)
if not exist data mkdir data
if not exist data\runs mkdir data\runs
echo [V] data\
if not exist systems.json (copy systems.json.example systems.json >nul && echo [V] systems.json נוצר מהתבנית) else (echo [V] systems.json קיים)
echo.
python discover.py || (echo [X] הגילוי נכשל && exit /b 1)
echo.
echo -------------------
echo מוכן. הצעדים הבאים:
echo   1. python server.py    ואז בדפדפן: http://127.0.0.1:17090
echo   2. ערוך את systems.json עם המערכות שלך ולחץ "רענן"
echo   3. hook לרישום אוטומטי - ההוראות ב-README
