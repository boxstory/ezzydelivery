@echo off
echo ========================================
echo Product ID Migration Fix
echo ========================================
echo.

cd /d "C:\00-web-dev\django-ezzydelivery\ezzydelivery"
call venvezdl\Scripts\activate

echo Checking current migration status...
python manage.py showmigrations product

echo.
echo Step 1: Rolling back to migration 0003 (if needed)...
python manage.py migrate product 0003_product_barcode_product_product_barcode_idx

echo.
echo Step 2: Applying new product_id migration...
python manage.py migrate product

echo.
echo ========================================
echo Done! Your site should work now.
echo Visit: http://127.0.0.1:8004/product/all/cards/
echo ========================================
echo.
echo Press any key to start the development server...
pause

echo.
echo Starting development server...
python manage.py runserver 8004
