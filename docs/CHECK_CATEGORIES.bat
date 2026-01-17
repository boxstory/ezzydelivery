@echo off
echo ============================================
echo   Checking Database Categories
echo ============================================
echo.

REM Try to activate virtual environment
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else if exist env\Scripts\activate.bat (
    call env\Scripts\activate.bat
)

python manage.py shell -c "exec(open('check_categories.py').read())"

echo.
pause
