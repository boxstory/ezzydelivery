#!/usr/bin/env bash
# Purpose: Pre-deploy gate — run before reloading gunicorn with new code.
# Used by: Manual deploys and Claude Code sessions (see CLAUDE.md).
# Notes: Fails fast on system-check errors, missing migrations, or test failures.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="/home/ezzyadmin/ezdlproject/venvezzy/bin/activate"

cd "$PROJECT_DIR"
# shellcheck disable=SC1090
source "$VENV"

echo "==> 1/4 System check (deploy)"
# check --deploy exits non-zero on ERRORS (warnings pass)
python manage.py check --deploy 2>&1 | grep -v "^\[INFO\]" | tail -4

echo "==> 2/5 Missing migrations check"
python manage.py makemigrations --check --dry-run > /dev/null

# A multi-line {# #} is not a comment — Django renders it as visible page text.
echo "==> 3/5 Template comment check"
python scripts/check_template_comments.py

echo "==> 4/5 Test suite"
python manage.py test --keepdb --noinput 2>&1 | tail -5

echo "==> 5/5 Collect static"
python manage.py collectstatic --noinput | tail -1

echo "PREDEPLOY GATE PASSED — safe to reload gunicorn:"
echo '  kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)'
