# 🎯 VS CODE SETUP & PROJECT WORKFLOW GUIDE

**Version:** 1.0
**Last Updated:** November 13, 2025
**Target:** All future Django projects
**Status:** Ready for implementation

---

## 📋 Table of Contents

1. [Initial Setup](#initial-setup)
2. [Git Workflow](#git-workflow)
3. [Project Analysis Phase](#project-analysis-phase)
4. [Development Workflow](#development-workflow)
5. [Testing & Verification](#testing--verification)
6. [Documentation Standards](#documentation-standards)
7. [Deployment Checklist](#deployment-checklist)
8. [Quick Reference](#quick-reference)

---

## 🚀 Initial Setup

### Phase 1: Environment Setup (15 minutes)

#### Step 1.1: Create Virtual Environment
```bash
# Navigate to project directory
cd /path/to/project

# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows)
venv\Scripts\activate

# Activate virtual environment (Linux/Mac)
source venv/bin/activate

# You should see (venv) prefix in terminal
```

**Checklist:**
- [ ] Virtual environment created
- [ ] Virtual environment activated
- [ ] (venv) prefix visible in terminal

#### Step 1.2: Install Project Dependencies
```bash
# Upgrade pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# For Django projects specifically
pip install django djangorestframework django-allauth django-cors-headers

# For development tools
pip install black flake8 pytest pytest-django coverage
```

**Checklist:**
- [ ] pip upgraded
- [ ] requirements.txt installed
- [ ] Django and dependencies installed
- [ ] Development tools installed

#### Step 1.3: Configure VS Code
```bash
# Install recommended extensions in VS Code
# 1. Python (ms-python.python)
# 2. Pylance (ms-python.vscode-pylance)
# 3. Black Formatter (ms-python.black-formatter)
# 4. Flake8 (ms-python.flake8)
# 5. Django (batisteo.vscode-django)
# 6. SQLite Viewer (alexcvzz.vscode-sqlite)
# 7. REST Client (humao.rest-client)
# 8. Thunder Client (rangav.vscode-thunder-client)
```

**Checklist:**
- [ ] All extensions installed
- [ ] Python interpreter selected (from venv)
- [ ] Linting configured (flake8)
- [ ] Formatter configured (black)

#### Step 1.4: Initialize Git Repository
```bash
# Initialize git
git init

# Configure git user
git config user.name "Your Name"
git config user.email "your.email@example.com"

# Create .gitignore
git add .gitignore
git commit -m "Initial commit: Add .gitignore"

# Create initial README
git add README.md
git commit -m "docs: Add initial README"
```

**Checklist:**
- [ ] Git initialized
- [ ] Git user configured
- [ ] .gitignore created
- [ ] Initial commit made

---

## 🌳 Git Workflow

### Rule #1: Always Run in Virtual Environment

```bash
# BEFORE ANY WORK: Activate venv
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# Should see (venv) prefix
(venv) $ _
```

**IMPORTANT:** ⚠️ Never run Django commands outside venv

### Rule #2: Git Commit After Each Major Phase

#### Phase Commit Structure
```
Phase → Implementation → Testing → Commit
```

#### Commit Message Format
```
[PHASE] type: description

PHASE: ANALYSIS, SETUP, SECURITY, FEATURE, FIX, TEST, DEPLOY
TYPE: feat, fix, docs, refactor, test, perf, security
```

#### Example Commits
```bash
# After project analysis
git add analysis/
git commit -m "docs: Add comprehensive project analysis report"

# After security fixes
git add users/views.py payments/views.py
git commit -m "security: Fix 5 critical security vulnerabilities"

# After feature implementation
git add features/
git commit -m "feat: Implement new user authentication system"

# After tests
git add tests/
git commit -m "test: Add 80% test coverage for critical functions"
```

#### Commit Frequency
- ✅ After each major task completion (30 min - 2 hour work)
- ✅ After all tests pass for a feature
- ✅ After documentation update
- ❌ NOT after each line of code
- ❌ NOT while work is incomplete or tests failing

#### Viewing Commit History
```bash
# View last 10 commits
git log --oneline -10

# View detailed commit
git log --stat

# View changes by commit
git diff HEAD~1 HEAD
```

---

## 🔍 Project Analysis Phase

### Step 1: Code Structure Analysis

#### 1.1 Project Layout Examination
```bash
# Understand directory structure
ls -la

# Identify main apps/modules
find . -type d -name "__pycache__" -prune -o -type d -print | sort

# For Django: check installed apps
python manage.py shell
>>> from django.conf import settings
>>> print(settings.INSTALLED_APPS)
```

**Tasks:**
- [ ] Map out project structure
- [ ] Identify all Django apps
- [ ] Document main dependencies
- [ ] Note any custom packages

#### 1.2 Code Quality Assessment
```bash
# Run linter
flake8 . --max-line-length=100

# Run type checker
mypy . --ignore-missing-imports

# Check code complexity
pylint --load-plugins pylint_django [app_name]/

# Check test coverage
pytest --cov=. --cov-report=html
```

**Tasks:**
- [ ] Identify style issues
- [ ] Document code quality gaps
- [ ] Note missing type hints
- [ ] Record test coverage percentage

#### 1.3 Security Assessment
```bash
# Check for common vulnerabilities
bandit -r . -ll

# Check dependencies for vulnerabilities
safety check

# Check for hardcoded secrets
detect-secrets scan

# Django security check
python manage.py check --deploy
```

**Tasks:**
- [ ] Identify security issues
- [ ] Check for hardcoded secrets
- [ ] Note missing validation
- [ ] Document exposure risks

---

### Step 2: Database Schema Analysis

#### 2.1 Model Examination
```bash
# View all models
python manage.py shell
>>> from django.apps import apps
>>> for model in apps.get_models():
...     print(model.__name__, model._meta.fields)

# Visualize database schema
python manage.py graph_models -a -o models.png

# Check migrations
python manage.py showmigrations
```

**Tasks:**
- [ ] Document all models
- [ ] Identify relationships
- [ ] Note missing indexes
- [ ] Check migration history

#### 2.2 Query Performance Analysis
```bash
# Enable query logging
# In settings.py:
LOGGING = {
    'loggers': {
        'django.db.backends': {
            'level': 'DEBUG',
        }
    }
}

# Identify N+1 queries
# Run app and check logs for duplicate queries
```

**Tasks:**
- [ ] Identify slow queries
- [ ] Find N+1 query problems
- [ ] Note missing indexes
- [ ] Document optimization opportunities

---

### Step 3: Feature & API Documentation

#### 3.1 API Endpoints Analysis
```bash
# For Django REST Framework
python manage.py shell
>>> from rest_framework.routers import DefaultRouter
>>> router = DefaultRouter()
>>> print(router.urls)

# List all URL patterns
python manage.py show_urls
```

**Tasks:**
- [ ] Document all endpoints
- [ ] Note authentication requirements
- [ ] Identify permission issues
- [ ] Check for rate limiting

#### 3.2 Business Logic Review
```bash
# Identify critical functions
grep -r "def " --include="*.py" | grep -v "__"

# Check for business logic in views
grep -r "business logic" --include="*.py"

# Find complex functions
grep -r "def " --include="*.py" | wc -l
```

**Tasks:**
- [ ] Map business logic
- [ ] Identify critical paths
- [ ] Note edge cases
- [ ] Document assumptions

---

### Step 4: Create Comprehensive Analysis Documents

#### 4.1 Project Architecture Document
```markdown
# Project Architecture

## Overview
- Project type: Django/Python
- Framework version: X.X
- Python version: X.X
- Database: PostgreSQL/MySQL/SQLite

## Technology Stack
- Web Framework: Django
- API: Django REST Framework
- Authentication: django-allauth
- Database ORM: Django ORM

## Project Structure
```
project/
├── apps/
│   ├── users/
│   ├── products/
│   └── orders/
├── config/
├── tests/
├── docs/
└── manage.py
```

## Key Components
- List main models
- List main views
- List main APIs

## Dependencies
- List critical dependencies
- Note security implications
```

**Checklist:**
- [ ] Architecture documented
- [ ] Tech stack listed
- [ ] Structure mapped
- [ ] Dependencies noted

#### 4.2 Security Assessment Report
```markdown
# Security Assessment

## Vulnerabilities Found
1. SQL Injection (2 locations)
2. IDOR (3 endpoints)
3. Missing authentication (5 views)
4. XSS (messaging system)

## Risk Assessment
| Issue | Severity | Location | Fix Time |
|-------|----------|----------|----------|
| Issue1 | CRITICAL | file.py:123 | 30 min |

## Recommendations
- [ ] Priority fixes
- [ ] Nice-to-have improvements
- [ ] Long-term refactoring
```

**Checklist:**
- [ ] All vulnerabilities identified
- [ ] Risk levels assigned
- [ ] Locations documented
- [ ] Fixes prioritized

#### 4.3 Code Quality Report
```markdown
# Code Quality Assessment

## Metrics
- Test Coverage: X%
- Code Duplication: X%
- Average Function Length: X lines
- Code Complexity: X

## Issues
- Missing type hints
- PEP8 violations
- Unused imports
- Missing docstrings

## Refactoring Opportunities
1. Extract reusable functions
2. Reduce code duplication
3. Improve naming conventions
```

**Checklist:**
- [ ] Metrics collected
- [ ] Issues identified
- [ ] Refactoring opportunities noted
- [ ] Priority set

#### 4.4 Performance Report
```markdown
# Performance Analysis

## Database Queries
- N+1 Query Problems: X locations
- Missing Indexes: X locations
- Slow Queries: X locations

## Recommendations
1. Implement select_related/prefetch_related
2. Add database indexes
3. Cache frequently accessed data
4. Optimize ORM queries
```

**Checklist:**
- [ ] Queries analyzed
- [ ] Bottlenecks identified
- [ ] Optimizations suggested
- [ ] Performance baselines recorded

---

### Analysis Phase Commit
```bash
git add docs/analysis/
git commit -m "docs: Add comprehensive project analysis reports

- Architecture documentation
- Security assessment
- Code quality analysis
- Performance evaluation"
```

---

## 💻 Development Workflow

### Standard Development Cycle

#### Phase 1: Planning (Before coding)
```bash
# 1. Read existing documentation
# 2. Check test coverage for area
# 3. Identify potential impacts
# 4. Plan implementation approach

# Always start in venv
(venv) $ which python
/path/to/venv/bin/python
```

#### Phase 2: Implementation (Write code)
```bash
# Create feature branch
git checkout -b feature/feature-name

# Write code
# Run linter frequently
flake8 [files]

# Format code
black [files]

# Run type check
mypy [files]
```

#### Phase 3: Testing (Test code)
```bash
# Run unit tests
pytest [test_file]

# Run all tests
pytest

# Check coverage
pytest --cov=. --cov-report=html

# Manual testing
python manage.py runserver
```

#### Phase 4: Verification (Verify everything works)
```bash
# Django system check
python manage.py check

# Run migrations
python manage.py migrate

# Verify no errors in logs
python manage.py test [app]
```

#### Phase 5: Commit (Save work)
```bash
# Stage changes
git add [files]

# Commit with message
git commit -m "type: description

- Bullet point 1
- Bullet point 2"

# Push to remote
git push origin feature/feature-name
```

---

### Code Quality Standards

#### 1. Linting Requirements
```bash
# Before committing, run:
flake8 . --max-line-length=100 --exclude=venv,migrations

# Fix issues automatically
autopep8 --in-place --aggressive --aggressive [file]
```

**Required:**
- [ ] No PEP8 violations
- [ ] No flake8 errors
- [ ] Line length ≤ 100 characters
- [ ] Proper imports

#### 2. Type Hints
```python
# Good
def get_user(user_id: int) -> User:
    return User.objects.get(id=user_id)

# Bad
def get_user(user_id):
    return User.objects.get(id=user_id)
```

**Required:**
- [ ] Function parameters typed
- [ ] Return types specified
- [ ] Type hints in complex functions

#### 3. Docstrings
```python
# Good
def create_order(user: User, items: List[Item]) -> Order:
    """
    Create a new order for the user.

    Args:
        user: The user placing the order
        items: List of items to include

    Returns:
        Order: The created order object

    Raises:
        ValueError: If items list is empty
    """
    pass

# Bad
def create_order(user, items):
    pass
```

**Required:**
- [ ] Module docstrings
- [ ] Function docstrings
- [ ] Class docstrings
- [ ] Complex logic comments

---

## 🧪 Testing & Verification

### Testing Workflow

#### Step 1: Unit Tests
```bash
# Run specific test
pytest tests/test_models.py::TestUserModel

# Run tests with coverage
pytest --cov=users --cov-report=term-missing

# Run all tests
pytest -v
```

**Target:**
- [ ] 80%+ coverage on critical code
- [ ] All critical functions tested
- [ ] Edge cases covered
- [ ] Error conditions tested

#### Step 2: Integration Tests
```bash
# Run Django test suite
python manage.py test

# Run specific app tests
python manage.py test users

# Run with verbosity
python manage.py test --verbosity=2
```

**Target:**
- [ ] APIs work end-to-end
- [ ] Database transactions work
- [ ] Authentication flows work
- [ ] Permissions enforced

#### Step 3: Security Tests
```bash
# Run security checks
python manage.py check --deploy

# Test authentication
pytest tests/test_auth.py

# Test permissions
pytest tests/test_permissions.py

# Manual security testing
# - Test CSRF protection
# - Test SQL injection prevention
# - Test XSS protection
# - Test authorization
```

**Target:**
- [ ] All security measures working
- [ ] No known vulnerabilities
- [ ] Authorization enforced
- [ ] Input validated

#### Step 4: Manual Testing
```bash
# Start development server
python manage.py runserver

# Test in browser
# Test all user flows
# Test all API endpoints
# Check for console errors
```

**Target:**
- [ ] UI works correctly
- [ ] APIs respond correctly
- [ ] No JavaScript errors
- [ ] Performance acceptable

---

## 📚 Documentation Standards

### Where to Save Files

#### Root Level (Entry Points Only)
```
project/
├── README.md (main entry point)
├── START_HERE.md (quick start)
├── .gitignore
├── requirements.txt
└── manage.py
```

#### Docs Folder (All Documentation)
```
project/docs/
├── analysis/ (project analysis)
│   ├── ARCHITECTURE.md
│   ├── CODE_QUALITY.md
│   ├── SECURITY.md
│   └── PERFORMANCE.md
├── security/ (security guides)
│   ├── VULNERABILITIES.md
│   ├── FIXES.md
│   └── BEST_PRACTICES.md
├── setup/ (setup guides)
│   ├── INSTALLATION.md
│   ├── CONFIGURATION.md
│   └── DATABASE.md
├── guides/ (feature guides)
│   ├── USER_MANAGEMENT.md
│   ├── API_USAGE.md
│   └── WORKFLOW.md
├── critical-fixes/ (fixes documentation)
│   ├── CRITICAL_ISSUES_FIXED.md
│   ├── BEFORE_AFTER_COMPARISON.md
│   └── QUICK_REFERENCE.md
└── VSCODE_SETUP_AND_WORKFLOW.md (this file)
```

**Rule:** 📌 **ALWAYS save new .md files in docs/ folder**

### Documentation Checklist

#### For Each Major Phase
- [ ] Create progress document
- [ ] Document issues found
- [ ] Document solutions implemented
- [ ] Document testing done
- [ ] Save to docs/[category]/
- [ ] Update docs/INDEX.md
- [ ] Commit to git

#### File Naming Convention
```
GOOD:
- CRITICAL_ISSUES_FIXED.md
- BEFORE_AFTER_COMPARISON.md
- IMPLEMENTATION_SUMMARY.md

BAD:
- fixes.md
- changes.md
- notes.md
```

#### README Format
```markdown
# Title

**Date:** Date created
**Status:** Status
**Updated:** Last update date

## Overview
Brief description

## Contents
- Section 1
- Section 2

## Quick Links
- Link to related docs

## Status
- [ ] Task 1
- [ ] Task 2
```

---

## ✅ Deployment Checklist

### Pre-Deployment (1 week before)

#### Code Quality
```bash
# Run all quality checks
flake8 .
black . --check
mypy .
pylint . --load-plugins pylint_django

# Run security checks
python manage.py check --deploy
bandit -r .
safety check
```

Checklist:
- [ ] No style issues
- [ ] No type errors
- [ ] No security issues
- [ ] No performance issues

#### Testing
```bash
# Run full test suite
pytest --cov=. --cov-report=term-missing

# Require minimum coverage
pytest --cov=. --cov-fail-under=80
```

Checklist:
- [ ] All tests passing
- [ ] Coverage ≥ 80%
- [ ] No flaky tests
- [ ] Load test results acceptable

#### Documentation
```bash
# Verify documentation exists
ls docs/
find docs/ -name "*.md" -type f | sort

# Check for broken links in docs
```

Checklist:
- [ ] Architecture documented
- [ ] API documented
- [ ] Deployment guide written
- [ ] Troubleshooting guide written

### Deployment (Deploy day)

```bash
# 1. Final backup
mysqldump -u user -p database > backup.sql

# 2. Pull latest code
git pull origin main

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run migrations
python manage.py migrate

# 5. Collect static files
python manage.py collectstatic --noinput

# 6. Run system checks
python manage.py check --deploy

# 7. Restart application
# (depends on deployment method)

# 8. Verify deployment
curl https://yourdomain.com/health/
```

Checklist:
- [ ] Backup created
- [ ] Code pulled
- [ ] Dependencies installed
- [ ] Migrations ran successfully
- [ ] Static files collected
- [ ] System checks passing
- [ ] Application responding
- [ ] No errors in logs

### Post-Deployment (After deployment)

```bash
# Check logs
tail -f /var/log/django/error.log

# Monitor metrics
# CPU, Memory, Database connections

# Test critical features
pytest tests/critical/

# Verify backups
ls -la backups/
```

Checklist:
- [ ] No errors in logs
- [ ] System metrics normal
- [ ] Critical features working
- [ ] Backups verified
- [ ] Rollback plan ready

---

## 🚀 Quick Reference

### Essential Commands

#### Virtual Environment
```bash
# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Deactivate
deactivate
```

#### Git
```bash
# Check status
git status

# Add changes
git add .

# Commit
git commit -m "message"

# Push
git push origin branch-name

# View log
git log --oneline -10
```

#### Django
```bash
# Run server
python manage.py runserver

# Make migrations
python manage.py makemigrations

# Migrate
python manage.py migrate

# Run tests
python manage.py test

# System check
python manage.py check
```

#### Code Quality
```bash
# Lint
flake8 .

# Format
black .

# Type check
mypy .

# Test coverage
pytest --cov=.
```

---

### Quick Workflow

#### Starting Work
```bash
# 1. Activate venv
(venv) $ _

# 2. Check status
git status

# 3. Update code
git pull

# 4. Create branch
git checkout -b feature/my-feature

# 5. Start coding
```

#### Ending Work Session
```bash
# 1. Run tests
pytest

# 2. Check quality
flake8 .

# 3. Stage changes
git add .

# 4. Commit
git commit -m "feat: description"

# 5. Push
git push origin feature/my-feature
```

---

## 📋 Summary Checklist

### Initial Setup
- [ ] Virtual environment created and activated
- [ ] Dependencies installed
- [ ] VS Code configured with extensions
- [ ] Git initialized and configured
- [ ] Project structure understood

### Before Each Work Session
- [ ] Virtual environment activated
- [ ] Latest code pulled
- [ ] Dependencies updated (if needed)
- [ ] Tests running

### During Development
- [ ] Code follows style guidelines
- [ ] Tests written and passing
- [ ] Code commented and documented
- [ ] No security issues introduced
- [ ] Performance impact considered

### After Each Major Phase
- [ ] All tests passing
- [ ] Code quality checks passing
- [ ] Documentation updated
- [ ] Git committed
- [ ] Changes verified

### Before Deployment
- [ ] Code review completed
- [ ] All tests passing (80%+ coverage)
- [ ] Security scan passing
- [ ] Documentation complete
- [ ] Deployment checklist complete

---

## 🎯 Final Notes

### Remember
1. ✅ **Always activate venv first** - CRITICAL!
2. ✅ **Commit after major phases** - Keeps history clean
3. ✅ **Save .md files to docs/ folder** - Organized structure
4. ✅ **Test before committing** - Catch issues early
5. ✅ **Document as you go** - Easier than retrospective docs

### Key Phrases
- "Is venv activated?" - Ask yourself every session
- "Did tests pass?" - Before every commit
- "Does this need documentation?" - For every major change
- "Is this saved to docs/?" - For every .md file
- "Will this scale?" - For every database query

---

**Created:** November 13, 2025
**Status:** Ready for implementation on all future projects
**Use for:** Django projects, Python projects, any VS Code development

Apply this workflow to every new project for consistent, professional development practices.
