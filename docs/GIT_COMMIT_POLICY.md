# Git Commit Policy - Significant Changes Only

This document describes the automated git commit policy implemented for the Django Ezzy Delivery project.

## 📋 Policy Overview

Commits are only allowed when **either** of the following conditions is met:

1. **Significant Changes**: Changes affect 3+ files OR modify 50+ lines
2. **Time-Based**: Last commit was made over 1 hour ago

This prevents excessive small commits while ensuring regular checkpoints.

---

## 🎯 Rationale

### Problems with Frequent Small Commits
- ❌ Clutters git history
- ❌ Makes code review difficult
- ❌ Obscures meaningful changes
- ❌ Wastes time creating commit messages

### Benefits of Significant Commits
- ✅ Clean, readable git history
- ✅ Each commit represents meaningful work
- ✅ Easier to review changes
- ✅ Better for rollbacks and cherry-picking
- ✅ More thoughtful commit messages

---

## ⚙️ Implementation

### Git Hook: pre-commit

**Location:** `.git/hooks/pre-commit` and `.git/hooks/pre-commit.ps1`

**How it works:**
1. Runs before every commit attempt
2. Checks staged changes against rules
3. Allows or rejects the commit
4. Shows clear feedback about why

### Configuration Values

```bash
MIN_FILES = 3                    # Minimum files changed
MIN_LINES = 50                   # Minimum lines changed
MIN_TIME_BETWEEN_COMMITS = 3600  # 1 hour in seconds
```

---

## 📊 Commit Rules

### Rule 1: Significant Changes

**Allowed when:**
- 3 or more files are modified, OR
- 50 or more lines are changed (additions + deletions)

**Examples:**

✅ **Allowed:**
```
Modified: 5 files, 30 lines   → 5 files ≥ 3 ✅
Modified: 2 files, 80 lines   → 80 lines ≥ 50 ✅
Modified: 3 files, 10 lines   → 3 files ≥ 3 ✅
```

❌ **Rejected:**
```
Modified: 2 files, 30 lines   → Needs 3+ files OR 50+ lines
Modified: 1 file, 40 lines    → Needs 3+ files OR 50+ lines
```

### Rule 2: Time-Based Commits

**Allowed when:**
- Last commit was made 60+ minutes ago

**Examples:**

✅ **Allowed:**
```
Last commit: 65 minutes ago  → Can commit small changes
Last commit: 2 hours ago     → Can commit small changes
Last commit: yesterday       → Can commit small changes
```

❌ **Rejected:**
```
Last commit: 30 minutes ago  → Wait 30 more minutes OR make more changes
Last commit: 45 minutes ago  → Wait 15 more minutes OR make more changes
```

---

## 🎬 Usage Examples

### Example 1: Significant Changes - Allowed

```bash
$ git add .
$ git commit -m "Add session timeout feature"

✅ Commit allowed:
   Files changed: 7 (minimum: 3)
   Lines changed: 285 (minimum: 50)
   Time since last commit: 30 minutes (minimum: 60)

[master abc1234] Add session timeout feature
 7 files changed, 285 insertions(+), 12 deletions(-)
```

### Example 2: Small Changes - Rejected

```bash
$ git add .
$ git commit -m "Fix typo"

❌ Commit rejected - Not significant enough:
   Files changed: 1 (need at least 3)
   Lines changed: 2 (need at least 50)
   Time since last commit: 15 minutes (need at least 60)

To force commit anyway, use: git commit --no-verify
```

### Example 3: Time-Based - Allowed

```bash
$ git add .
$ git commit -m "Update README"

✅ Commit allowed:
   Files changed: 1 (minimum: 3)
   Lines changed: 10 (minimum: 50)
   Time since last commit: 75 minutes (minimum: 60)

[master def5678] Update README
 1 file changed, 10 insertions(+), 5 deletions(-)
```

---

## 🚨 Bypassing the Hook

### When to Bypass

You should bypass the hook in these cases:
- **Hotfix:** Critical bug that needs immediate commit
- **End of Day:** Need to commit work before leaving
- **Collaboration:** Teammate needs your changes urgently
- **Deployment:** Production deployment requires commit

### How to Bypass

Use the `--no-verify` flag:

```bash
git commit -m "Hotfix: Critical security patch" --no-verify
```

**Warning:** Use sparingly! The policy exists for good reasons.

---

## 📈 Impact on Claude Code

### Before Policy (Old Behavior)
```
Commit after every small change:
- Fix typo          (1 file, 1 line)
- Add comment       (1 file, 2 lines)
- Update variable   (1 file, 1 line)
- Format code       (1 file, 5 lines)

Result: 4 commits for minor changes
```

### After Policy (New Behavior)
```
Accumulate changes until significant:
- Fix typo          (1 file, 1 line)
- Add comment       (1 file, 2 lines)
- Update variable   (1 file, 1 line)
- Format code       (1 file, 5 lines)
- Add new feature   (3 files, 100 lines)

Result: 1 meaningful commit
```

### Claude Code Integration

When Claude Code wants to create a commit:
1. **Checks hook** - Runs pre-commit validation
2. **If allowed** - Commit proceeds normally
3. **If rejected** - Claude Code continues working
4. **Accumulates** - More changes until significant
5. **Commits later** - When rules are met

**Note:** Claude Code can still use `git commit --no-verify` for important commits when needed.

---

## 🔧 Configuration

### Changing Thresholds

**To require more files per commit:**

Edit `.git/hooks/pre-commit.ps1`:
```powershell
$MIN_FILES = 5  # Change from 3 to 5
```

**To require more lines changed:**

Edit `.git/hooks/pre-commit.ps1`:
```powershell
$MIN_LINES = 100  # Change from 50 to 100
```

**To change time between commits:**

Edit `.git/hooks/pre-commit.ps1`:
```powershell
$MIN_TIME_BETWEEN_COMMITS = 7200  # 2 hours instead of 1
```

### Disabling the Policy

**Temporarily (single commit):**
```bash
git commit --no-verify
```

**Permanently:**
```bash
# Rename the hook file
mv .git/hooks/pre-commit .git/hooks/pre-commit.disabled
mv .git/hooks/pre-commit.ps1 .git/hooks/pre-commit.ps1.disabled
```

---

## 📊 Statistics & Monitoring

### Tracking Commit Quality

**Check average commit size:**
```bash
git log --shortstat --since="1 month ago" | \
  grep "files changed" | \
  awk '{files+=$1; inserted+=$4; deleted+=$6} END {print "Avg files:", files/NR, "Avg lines:", (inserted+deleted)/NR}'
```

**Check commit frequency:**
```bash
git log --since="1 month ago" --pretty=format:"%h %ad" --date=short | \
  awk '{print $2}' | uniq -c
```

### Recommended Metrics

Good commit practices:
- **Files per commit:** 3-10 files (sweet spot)
- **Lines per commit:** 50-500 lines
- **Commits per day:** 2-5 commits
- **Commit message quality:** Descriptive, not "wip" or "fix"

---

## 🎓 Best Practices

### Writing Good Commit Messages

Since commits are less frequent, make them count:

✅ **Good commit messages:**
```
Add user session timeout after 1 hour of inactivity

Implement automatic logout system with:
- Django session configuration
- Custom middleware for tracking
- JavaScript monitor with warning modal
- Integration with all dashboards

Fixes #123
```

❌ **Bad commit messages:**
```
update
fix stuff
wip
changes
```

### Organizing Your Work

**Work in logical chunks:**
1. Complete a full feature
2. Fix related bugs together
3. Refactor a complete module
4. Update related documentation

**Don't:**
- Make changes across unrelated features
- Mix features with bug fixes
- Include unrelated formatting changes

---

## 🐛 Troubleshooting

### Hook Not Running

**Check if hook exists:**
```powershell
Test-Path .git\hooks\pre-commit.ps1
```

**Check if Git can execute PowerShell:**
```bash
git config --global core.hooksPath .git/hooks
```

### Hook Failing

**Test the hook manually:**
```powershell
# Stage some changes
git add .

# Run hook directly
powershell -ExecutionPolicy Bypass -File .git\hooks\pre-commit.ps1
```

### Permission Issues

**On Windows:**
```powershell
# Allow PowerShell scripts
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**On Linux/Mac:**
```bash
# Make hook executable
chmod +x .git/hooks/pre-commit
```

---

## 📚 Related Documentation

- [Git Hooks Documentation](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Writing Good Commit Messages](https://chris.beams.io/posts/git-commit/)

---

## 🎯 Summary

### What This Policy Does

✅ Prevents tiny, meaningless commits
✅ Ensures regular checkpoints (every hour minimum)
✅ Encourages thoughtful, complete work
✅ Keeps git history clean and reviewable
✅ Allows bypassing for urgent situations

### What This Policy Does NOT Do

❌ Prevent you from committing urgently (use --no-verify)
❌ Replace code review
❌ Guarantee commit quality (still need good messages)
❌ Work without git hooks installed

### Quick Reference

```bash
# Normal commit (will check rules)
git commit -m "Your message"

# Bypass rules (emergency only)
git commit -m "Your message" --no-verify

# Check if you can commit
powershell -File .git\hooks\pre-commit.ps1

# View current policy settings
Get-Content .git\hooks\pre-commit.ps1 | Select-String "MIN_"
```

---

**Implementation Date:** 2025-11-20
**Policy Status:** ✅ Active
**Applies To:** All commits to this repository
