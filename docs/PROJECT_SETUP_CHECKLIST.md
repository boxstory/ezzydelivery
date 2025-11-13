# ✅ PROJECT SETUP CHECKLIST

**For:** All new Django/Python projects using VS Code
**Version:** 1.0
**Created:** November 13, 2025

---

## 🚀 PHASE 1: Initial Environment Setup (15 min)

### Create Virtual Environment
```bash
python -m venv venvezdl
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
```
- [ ] venvezdl created
- [ ] venvezdl activated (see (venv) prefix)

### Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install django djangorestframework pytest pytest-django black flake8
```
- [ ] pip upgraded
- [ ] requirements.txt installed
- [ ] dev tools installed

### Configure VS Code
- [ ] Python extension installed (ms-python.python)
- [ ] Pylance installed (ms-python.vscode-pylance)
- [ ] Black Formatter installed
- [ ] Flake8 installed
- [ ] Django extension installed
- [ ] Python interpreter set to venv

### Initialize Git
```bash
git init
git config user.name "Your Name"
git config user.email "your.email@example.com"
```
- [ ] git initialized
- [ ] user configured
- [ ] .gitignore created
- [ ] first commit made

---

## 🔍 PHASE 2: Project Analysis (2-3 hours)

### Code Structure Analysis
```bash
ls -la
find . -type d -name "__pycache__" -prune -o -type d -print | sort
python manage.py shell  # Check installed apps
```
- [ ] Project structure mapped
- [ ] All apps identified
- [ ] Main dependencies documented

### Code Quality Check
```bash
flake8 .
mypy .
pylint --load-plugins pylint_django [app]
pytest --cov=. --cov-report=html
```
- [ ] Linting issues documented
- [ ] Type hints checked
- [ ] Code complexity noted
- [ ] Test coverage measured

### Security Assessment
```bash
python manage.py check --deploy
bandit -r . -ll
safety check
detect-secrets scan
```
- [ ] Vulnerabilities identified
- [ ] Locations documented
- [ ] Risk levels assigned
- [ ] Recommendations noted

### Database Analysis
```bash
python manage.py showmigrations
python manage.py shell
# >>> from django.apps import apps
# >>> for model in apps.get_models(): print(model.__name__)
```
- [ ] All models documented
- [ ] Relationships mapped
- [ ] Indexes checked
- [ ] Migration history reviewed

### Performance Analysis
```bash
# Enable query logging and run app
# Look for N+1 queries, missing indexes, slow queries
```
- [ ] N+1 queries identified
- [ ] Missing indexes noted
- [ ] Slow queries found
- [ ] Optimization opportunities listed

### Create Analysis Documents
- [ ] ARCHITECTURE.md created
- [ ] SECURITY_ASSESSMENT.md created
- [ ] CODE_QUALITY_REPORT.md created
- [ ] PERFORMANCE_REPORT.md created
- [ ] Save all to docs/analysis/

### Commit Analysis
```bash
git add docs/analysis/
git commit -m "docs: Add comprehensive project analysis"
```
- [ ] Analysis documents committed
- [ ] Commit message clear
- [ ] History clean

---

## ⚙️ PHASE 3: Setup & Configuration (1-2 hours)

### Environment Setup
- [ ] .env file created with secrets
- [ ] Database configured
- [ ] Email backend configured
- [ ] Static files configured
- [ ] Media files configured

### Project Settings
```bash
python manage.py check
```
- [ ] DEBUG set correctly
- [ ] ALLOWED_HOSTS configured
- [ ] DATABASES configured
- [ ] INSTALLED_APPS complete
- [ ] MIDDLEWARE configured
- [ ] System checks passing

### Testing Setup
```bash
pytest --version
python manage.py test --help
```
- [ ] pytest configured
- [ ] Django tests working
- [ ] Coverage tracking enabled
- [ ] Test database setup

### Development Tools
- [ ] Code formatter configured (black)
- [ ] Linter configured (flake8)
- [ ] Pre-commit hooks installed
- [ ] Git hooks configured

### Commit Setup
```bash
git add .
git commit -m "setup: Configure project environment and settings"
```
- [ ] Configuration committed
- [ ] Secrets NOT committed (.env in .gitignore)
- [ ] Settings verified

---

## 📝 PHASE 4: Development Workflow

### Before Starting Each Day
```bash
# 1. Activate venv
(venv) $ _

# 2. Pull latest
git pull origin main

# 3. Update deps if needed
pip install -r requirements.txt

# 4. Check status
python manage.py check
```
- [ ] venv activated
- [ ] code updated
- [ ] dependencies fresh
- [ ] system healthy

### During Development
```bash
# 1. Create feature branch
git checkout -b feature/description

# 2. Write code
# Code here...

# 3. Run tests frequently
pytest

# 4. Check quality
flake8 .
black . --check

# 5. Run system check
python manage.py check
```
- [ ] Feature branch created
- [ ] Code written
- [ ] Tests passing
- [ ] Code quality OK
- [ ] Type hints present
- [ ] Docstrings added

### After Completing Feature
```bash
# 1. Run full test suite
pytest --cov=. --cov-fail-under=80

# 2. Final quality check
flake8 .
black .
mypy .

# 3. Verify migrations
python manage.py check

# 4. Create commit
git add .
git commit -m "feat: Add feature description

- Bullet point 1
- Bullet point 2"

# 5. Push to remote
git push origin feature/description
```
- [ ] All tests passing
- [ ] Coverage > 80%
- [ ] Code formatted
- [ ] Type hints added
- [ ] Docstrings added
- [ ] Commit message clear
- [ ] Changes pushed

---

## 🧪 PHASE 5: Testing Requirements

### Unit Tests (Target: 80%+ coverage)
```bash
pytest tests/ --cov=. --cov-report=term-missing
```
- [ ] Models tested
- [ ] Views tested
- [ ] Forms tested
- [ ] Utils tested
- [ ] Services tested

### Integration Tests
```bash
python manage.py test
```
- [ ] APIs working end-to-end
- [ ] Database transactions OK
- [ ] Authentication flows OK
- [ ] Permissions enforced

### Security Tests
```bash
python manage.py check --deploy
pytest tests/security/
```
- [ ] CSRF protection working
- [ ] SQL injection prevented
- [ ] XSS prevented
- [ ] Authorization enforced
- [ ] Rate limiting working

### Performance Tests
```bash
# Run app and monitor
python manage.py runserver
# Check: response times, database queries, memory usage
```
- [ ] Response times acceptable
- [ ] Database queries optimized
- [ ] Memory usage normal
- [ ] No N+1 queries

### Manual Testing
- [ ] All user flows tested
- [ ] All API endpoints tested
- [ ] Error handling tested
- [ ] Edge cases tested
- [ ] No console errors

---

## 📚 PHASE 6: Documentation Requirements

### Save Location Rule
**✅ ALWAYS save .md files to docs/ folder**

### Required Documentation
- [ ] README.md (root, entry point)
- [ ] START_HERE.md (root, quick start)
- [ ] docs/analysis/ (project analysis)
- [ ] docs/security/ (security docs)
- [ ] docs/setup/ (setup guides)
- [ ] docs/guides/ (feature guides)
- [ ] docs/[category]/ (issue documentation)

### Documentation for Each Major Phase
- [ ] Progress document created
- [ ] Issues documented
- [ ] Solutions documented
- [ ] Testing documented
- [ ] Saved to docs/[category]/
- [ ] INDEX.md updated
- [ ] Committed to git

### Code Documentation
- [ ] Module docstrings present
- [ ] Function docstrings present
- [ ] Complex logic commented
- [ ] Type hints complete
- [ ] README files in each app

---

## ✅ PHASE 7: Quality Gates (Before Commit)

### Code Quality Checklist
```bash
flake8 .  # No style issues
black .   # Formatted
mypy .    # Type hints OK
pylint .  # No major issues
```
- [ ] PEP8 compliant
- [ ] Black formatted
- [ ] Type hints present
- [ ] Linter passing

### Security Checklist
```bash
python manage.py check --deploy
bandit -r .
safety check
```
- [ ] No security warnings
- [ ] No vulnerabilities
- [ ] Dependencies safe

### Testing Checklist
```bash
pytest --cov=. --cov-fail-under=80
python manage.py test
```
- [ ] All tests passing
- [ ] Coverage > 80%
- [ ] No flaky tests
- [ ] Integration tests OK

### Git Checklist
```bash
git status           # No untracked files
git diff            # Review changes
git log --oneline   # Clear history
```
- [ ] Only necessary files staged
- [ ] Commit message clear
- [ ] No secrets in commit
- [ ] Related changes grouped

---

## 🚀 PHASE 8: Deployment Checklist (1 week before)

### Code Quality
```bash
flake8 .
black . --check
mypy .
python manage.py check --deploy
```
- [ ] No style issues
- [ ] No type errors
- [ ] No security issues

### Testing
```bash
pytest --cov=. --cov-fail-under=80
python manage.py test
```
- [ ] All tests passing
- [ ] Coverage ≥ 80%
- [ ] Integration tests OK
- [ ] Load test passed

### Documentation
- [ ] API documented
- [ ] Deployment guide written
- [ ] Troubleshooting guide written
- [ ] Architecture documented

### Database
- [ ] Migrations tested
- [ ] Backup strategy defined
- [ ] Rollback plan ready
- [ ] Performance OK

### Configuration
- [ ] Environment variables set
- [ ] Settings verified
- [ ] Secrets secured
- [ ] Logging configured

---

## 🎯 CRITICAL REMINDERS

### Rule 1: Always Use Virtual Environment
```bash
# EVERY SESSION START:
(venv) $ _  # Should see (venv) prefix

# If not activated:
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
```
⚠️ **CRITICAL:** Never run Django outside venv

### Rule 2: Commit After Major Phases
```bash
# NOT: Every line
# NOT: Broken code
# YES: After feature complete
# YES: After tests pass
# YES: After documentation
```
✅ **Pattern:** Implementation → Testing → Commit

### Rule 3: Save .md Files to docs/
```bash
# NOT: Save to root
# YES: Save to docs/[category]/
```
📌 **Always:** docs/analysis/, docs/security/, docs/guides/, etc.

### Rule 4: Test Before Committing
```bash
# BEFORE git commit:
pytest           # Tests pass
flake8 .         # No style issues
python manage.py check  # System OK
```
✅ **Never:** Commit broken code

### Rule 5: Clear Commit Messages
```bash
# GOOD:
git commit -m "feat: Add user registration with email verification"

# BAD:
git commit -m "changes"
git commit -m "fix stuff"
git commit -m "WIP"
```
📝 **Format:** [type] description (feat/fix/docs/test/refactor/security)

---

## 🏃 Quick Start (New Project)

### Day 1 (2 hours)
1. [ ] Create venv
2. [ ] Install dependencies
3. [ ] Configure VS Code
4. [ ] Initialize git
5. [ ] First commit

### Day 2-4 (6-12 hours)
1. [ ] Analyze project
2. [ ] Create analysis docs
3. [ ] Identify issues
4. [ ] Commit analysis

### Day 5+ (Ongoing)
1. [ ] Setup configuration
2. [ ] Run system checks
3. [ ] Begin development
4. [ ] Test & commit regularly
5. [ ] Document as you go

---

## 📞 Quick Links

- **Full Guide:** See `VSCODE_SETUP_AND_WORKFLOW.md`
- **Git Help:** `git --help`
- **Django Help:** `python manage.py help`
- **pytest Help:** `pytest --help`

---

**Status:** ✅ Ready to use
**Last Updated:** November 13, 2025
**Apply to:** All future Django/Python projects

