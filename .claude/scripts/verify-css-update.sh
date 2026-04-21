#!/bin/bash
# CSS Update Verification Script
# Ensures CSS changes are properly copied, collected, and cached-busted
# Usage: ./verify-css-update.sh <app> <css-filename>
# Example: ./verify-css-update.sh workforce cod_settlement_report.css

set -e

if [ $# -lt 2 ]; then
    echo "Usage: $0 <app> <css-filename>"
    echo "Example: $0 workforce cod_settlement_report.css"
    exit 1
fi

APP=$1
CSS_FILE=$2
SOURCE_CSS="/home/ezzyadmin/ezdlproject/ezzydelivery/${APP}/static/${APP}/css/${CSS_FILE}"
STATIC_CSS="/home/ezzyadmin/ezdlproject/ezzydelivery/staticroot/${APP}/css/${CSS_FILE}"
TEMPLATE_DIR="/home/ezzyadmin/ezdlproject/ezzydelivery/${APP}/templates/${APP}/"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "CSS UPDATE VERIFICATION: $APP/$CSS_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Verify source CSS exists
echo ""
echo "✓ Step 1: Checking source CSS..."
if [ ! -f "$SOURCE_CSS" ]; then
    echo "❌ ERROR: Source CSS not found: $SOURCE_CSS"
    exit 1
fi
SOURCE_SIZE=$(stat -f%z "$SOURCE_CSS" 2>/dev/null || stat -c%s "$SOURCE_CSS" 2>/dev/null)
SOURCE_TIME=$(stat -f%Sm -t "%Y-%m-%d %H:%M:%S" "$SOURCE_CSS" 2>/dev/null || stat -c%y "$SOURCE_CSS" 2>/dev/null | cut -d' ' -f1-2)
echo "  Source: $SOURCE_CSS"
echo "  Size: ${SOURCE_SIZE} bytes"
echo "  Modified: ${SOURCE_TIME}"

# Step 2: Copy to staticroot
echo ""
echo "✓ Step 2: Copying to staticroot..."
cp "$SOURCE_CSS" "$STATIC_CSS"
if [ ! -f "$STATIC_CSS" ]; then
    echo "❌ ERROR: Failed to copy CSS to staticroot"
    exit 1
fi
STATIC_SIZE=$(stat -f%z "$STATIC_CSS" 2>/dev/null || stat -c%s "$STATIC_CSS" 2>/dev/null)
echo "  Destination: $STATIC_CSS"
echo "  Size: ${STATIC_SIZE} bytes"
if [ "$SOURCE_SIZE" -ne "$STATIC_SIZE" ]; then
    echo "❌ ERROR: File size mismatch after copy!"
    exit 1
fi
echo "  ✓ Copy verified"

# Step 3: Run collectstatic
echo ""
echo "✓ Step 3: Running collectstatic..."
source /home/ezzyadmin/ezdlproject/venvezzy/bin/activate
cd /home/ezzyadmin/ezdlproject/ezzydelivery
python manage.py collectstatic --noinput > /tmp/collectstatic.log 2>&1
if grep -q "copied\|unmodified" /tmp/collectstatic.log; then
    echo "  ✓ collectstatic completed"
else
    echo "  ⚠ collectstatic warning - check log:"
    tail -5 /tmp/collectstatic.log
fi

# Step 4: Check CSS syntax
echo ""
echo "✓ Step 4: Checking CSS syntax..."
if command -v csslint &> /dev/null; then
    csslint "$SOURCE_CSS" 2>/dev/null || echo "  ⚠ CSS lint warnings (non-critical)"
else
    echo "  ℹ csslint not installed, skipping"
fi

# Step 5: Find and update template version
echo ""
echo "✓ Step 5: Bumping cache version in templates..."
TEMPLATE_PATTERN="${CSS_FILE%.css}"
CURRENT_DATE=$(date +%Y%m%d)
RANDOM_CHAR=$(printf \\$(printf '%03o' $((RANDOM % 26 + 97))))

# Find template files that reference this CSS
TEMPLATE_FILES=$(find "$TEMPLATE_DIR" -name "*.html" -exec grep -l "$CSS_FILE" {} \;)
if [ -z "$TEMPLATE_FILES" ]; then
    echo "  ℹ No templates found referencing $CSS_FILE"
else
    echo "  Found templates:"
    for TEMPLATE in $TEMPLATE_FILES; do
        echo "    - $TEMPLATE"
        # Update version from v=YYYYMMDDx to v=YYYYMMDDy
        sed -i "s/\?v=${CURRENT_DATE}[a-z]/\?v=${CURRENT_DATE}${RANDOM_CHAR}/g" "$TEMPLATE"
        NEW_VERSION=$(grep -o "\?v=[0-9]*[a-z]" "$TEMPLATE" | head -1)
        echo "      Updated to: $NEW_VERSION"
    done
fi

# Step 6: Reload server
echo ""
echo "✓ Step 6: Reloading Gunicorn..."
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1) 2>/dev/null && echo "  ✓ Server reloaded" || echo "  ⚠ Gunicorn not found"

# Step 7: Final verification
echo ""
echo "✓ Step 7: Final verification..."
sleep 1
if [ -f "$STATIC_CSS" ]; then
    FINAL_SIZE=$(stat -f%z "$STATIC_CSS" 2>/dev/null || stat -c%s "$STATIC_CSS" 2>/dev/null)
    echo "  ✓ CSS file exists in staticroot"
    echo "  ✓ Size: ${FINAL_SIZE} bytes"
    echo "  ✓ Ready to serve"
else
    echo "❌ ERROR: CSS not found in staticroot after collectstatic!"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ CSS UPDATE VERIFICATION COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "  1. Hard refresh browser: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)"
echo "  2. Open DevTools > Network tab > filter for CSS"
echo "  3. Verify new version (?v=${CURRENT_DATE}${RANDOM_CHAR}) is loaded"
echo ""
