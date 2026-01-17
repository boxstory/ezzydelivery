@echo off
echo ============================================
echo   Adding Product Categories
echo ============================================
echo.

REM Try to activate virtual environment
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else if exist .venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
) else if exist env\Scripts\activate.bat (
    echo Activating virtual environment...
    call env\Scripts\activate.bat
) else (
    echo WARNING: Virtual environment not found. Using system Python.
)

echo.
echo Running setup script...
python manage.py shell -c "exec(open('setup_categories.py').read())"

echo.
echo ============================================
echo   Done!
echo ============================================
echo.
pause
