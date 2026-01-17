@echo off
echo ========================================
echo SIMPLE Product ID Fix
echo ========================================
echo.

cd /d "C:\00-web-dev\django-ezzydelivery\ezzydelivery"
call venvezdl\Scripts\activate

echo Step 1: Checking migration status...
python manage.py showmigrations product

echo.
echo Step 2: Rolling back to migration 0003...
python manage.py migrate product 0003

echo.
echo Step 3: Applying product_id migration (0004)...
python manage.py migrate product 0004

echo.
echo ========================================
echo ✅ DONE! Product ID system is ready!
echo ========================================
echo.
echo Test your site: http://127.0.0.1:8004/product/all/cards/
echo.
echo Press any key to start the server...
pause

python manage.py runserver 8004
