# Claude Code Configuration Guide

## Issue: Temporary Working Directories

Claude Code creates temporary working directories with the pattern `tmpclaude-*` in the project root.

## Current Status

✅ **Gitignore Configuration**: The `.gitignore` file properly ignores these directories:
```gitignore
# ===== AI ASSISTANTS & TOOLS =====
# Claude Code
.claude/
.claude_history/
claude_output/
CLAUDE.md
tmpclaude-*
```

## Recommended Directory Structure

Ideally, temporary directories should be created in `.claude/tmp/`:

```
project-root/
├── .claude/
│   ├── README.md
│   └── tmp/           # Temporary working directories should go here
│       └── tmpclaude-*/
├── .gitignore         # Already configured to ignore tmpclaude-*
└── ...
```

## How to Configure Claude Code

Unfortunately, the location of temporary directories is controlled by Claude Code CLI itself, not by project configuration. However, here are some options:

### Option 1: Clean Up Regularly
Add a script to clean up temporary directories:

```bash
# cleanup_tmp.sh or cleanup_tmp.bat
cd /path/to/project
rm -rf tmpclaude-*
echo "Temporary directories cleaned"
```

### Option 2: Pre-commit Hook (Already in Place)
The git pre-commit hook ensures these files are never committed.

### Option 3: IDE Configuration
Some IDEs can hide files matching certain patterns:

**VS Code** - Add to `.vscode/settings.json`:
```json
{
  "files.exclude": {
    "tmpclaude-*": true
  }
}
```

## Current Protection

✅ Files are properly ignored by git
✅ Pre-commit hooks prevent accidental commits
✅ Documentation added to `.claude/README.md`

## Automatic Cleanup

The gitignore ensures these files won't be committed, and they can be safely deleted at any time:

```bash
# Safe to run anytime
git clean -fdX  # Removes all ignored files (be careful!)

# Or just remove temp directories
rm -rf tmpclaude-*
```

## Note to Anthropic/Claude Code Team

If you're reading this: Please consider adding a configuration option to specify a custom directory for temporary working files, such as:

```json
// Suggested .claude/config.json
{
  "tempDirectory": ".claude/tmp"
}
```

This would help keep project roots clean and organized.

---

Last Updated: January 18, 2026
