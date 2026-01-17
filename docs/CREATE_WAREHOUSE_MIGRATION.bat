@echo off
echo ============================================
echo   Create Warehouse System Migration
echo ============================================
echo.

REM Try to activate virtual environment
if exist venvezdl\Scripts\activate.bat (
    echo Activating virtual environment (venvezdl)...
    call venvezdl\Scripts\activate.bat
) else if exist venv\Scripts\activate.bat (
    echo Activating virtual environment (venv)...
    call venv\Scripts\activate.bat
) else if exist .venv\Scripts\activate.bat (
    echo Activating virtual environment (.venv)...
    call .venv\Scripts\activate.bat
) else if exist env\Scripts\activate.bat (
    echo Activating virtual environment (env)...
    call env\Scripts\activate.bat
) else (
    echo WARNING: Virtual environment not found. Using system Python.
    echo.
)

echo.
echo ============================================
echo   Step 1: Create Migration
echo ============================================
echo.
python manage.py makemigrations warehouse --name restructure_warehouse_system

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to create migration!
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Step 2: Show Migration SQL (Preview)
echo ============================================
echo.
set /p preview="Do you want to preview the SQL? (Y/N): "

if /i "%preview%"=="Y" (
    echo.
    echo Showing migration SQL...
    python manage.py sqlmigrate warehouse restructure_warehouse_system
)

echo.
echo ============================================
echo   Step 3: Apply Migration
echo ============================================
echo.
set /p apply="Do you want to apply the migration now? (Y/N): "

if /i "%apply%"=="Y" (
    echo.
    echo Applying migration...
    python manage.py migrate warehouse

    if %ERRORLEVEL% EQU 0 (
        echo.
        echo ============================================
        echo   SUCCESS! Migration Applied
        echo ============================================
        echo.
        echo Next steps:
        echo 1. Go to Django Admin: http://127.0.0.1:8004/admin/
        echo 2. Navigate to Warehouse section
        echo 3. Create your first fulfillment center
        echo.
    ) else (
        echo.
        echo ERROR: Migration failed!
        echo Check the error messages above.
        echo.
    )
) else (
    echo.
    echo Migration created but NOT applied.
    echo To apply later, run:
    echo   python manage.py migrate warehouse
    echo.
)

echo.
echo ============================================
echo   Done!
echo ============================================
echo.
pause
