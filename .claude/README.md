# Claude Code Configuration

This directory contains Claude Code configuration and temporary files.

## Directory Structure

```
.claude/
├── README.md           # This file
└── tmp/               # Temporary working directories (recommended location)
```

## Temporary Working Directories

Claude Code may create temporary working directories with the pattern `tmpclaude-*`.

### Current Behavior
By default, these directories may be created in the project root.

### Recommended Configuration
Temporary directories should be created within `.claude/tmp/` to keep the project root clean.

### Gitignore Rules
The following patterns are ignored in `.gitignore`:
- `.claude/` - Entire Claude directory (except this README if committed)
- `tmpclaude-*` - Temporary directories anywhere in the project

## Notes

- All contents of `.claude/` are automatically ignored by git
- This folder is safe for temporary files and Claude-specific data
- Do not commit sensitive information to this directory
