@echo off
echo ============================================
echo   Create Fulfillment Stores
echo   For Existing Businesses
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
) else if exist venvezdl\Scripts\activate.bat (
    echo Activating virtual environment...
    call venvezdl\Scripts\activate.bat
) else (
    echo WARNING: Virtual environment not found. Using system Python.
)

echo.
echo ============================================
echo   Option 1: Dry Run (Preview Only)
echo ============================================
echo.
set /p preview="Do you want to preview first? (Y/N): "

if /i "%preview%"=="Y" (
    echo.
    echo Running preview...
    python manage.py create_fulfillment_stores --dry-run
    echo.
    echo ============================================
    echo   Preview Complete
    echo ============================================
    echo.
    set /p continue="Do you want to create the stores now? (Y/N): "

    if /i "%continue%"=="Y" (
        echo.
        echo Creating fulfillment stores...
        python manage.py create_fulfillment_stores
    ) else (
        echo.
        echo Operation cancelled.
    )
) else (
    echo.
    echo Creating fulfillment stores...
    python manage.py create_fulfillment_stores
)

echo.
echo ============================================
echo   Done!
echo ============================================
echo.
pause
