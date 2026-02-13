# docs/ Folder Merge Analysis

**Goal:** Determine which docs should stay in `docs/` vs `.claude/`

---

## Current Structure

### docs/ (Project-wide documentation - 100+ files)
User guides, API docs, deployment checklists, architecture docs
**Purpose:** Public/team documentation, onboarding, reference

### .claude/ (Claude-specific configuration)
Skills, commands, plans, summaries, scripts
**Purpose:** AI assistant configuration, automation, testing

---

## Recommended Organization

### Keep in `docs/` (User-Facing Documentation)
✅ **API & Integration Guides**
- API_DOCUMENTATION.md
- API_TESTER_GUIDE.md
- N8N_WEBHOOK_SETUP.md

✅ **Deployment & Production**
- DEPLOYMENT_CHECKLIST.md
- PRODUCTION_READINESS_CHECKLIST.md
- VSCODE_SETUP_AND_WORKFLOW.md

✅ **System Architecture**
- ADDRESS_VERIFICATION_SYSTEM.md
- COD_WALLET_IMPLEMENTATION.md
- USER_VERIFICATION_SYSTEM.md
- WAREHOUSE_SYSTEM_GUIDE.md

✅ **Developer Guides**
- CODING_STANDARDS.md
- GIT_COMMIT_POLICY.md
- BRAND_KIT_REFERENCE.md
- CSS_JS_ARCHITECTURE.md

✅ **Business/Marketing**
- 100_Marketing_FAQs_Reference.md
- Ezzy_Delivery_100_Marketing_FAQs.txt
- SEO_IMPLEMENTATION_COMPLETE.md

✅ **Feature Specs**
- FLUTTER_DRIVER_APP_SPEC.md
- DRIVER_DASHBOARD_ENHANCEMENTS.md
- STAFF_DASHBOARD_FEATURES.md

### Move to `.claude/docs/` (AI/Automation Documentation)
📦 **Testing & QA**
- warehouse_testing_todos.md (already there)
- qa_todos.md → `.claude/docs/qa_todos.md`
- TEST_SUMMARY.md → `.claude/summaries/test_summary.md`

📦 **Session Notes & Fixes**
- server-fix-checklist-2026-01-21.md (already there)
- SESSION_SUMMARY.md → `.claude/summaries/session_summary.md`
- COMMIT_SUMMARY_*.md → `.claude/summaries/`

📦 **Implementation Tracking**
- BUGS-AND-ISSUES.md → `.claude/docs/bugs_and_issues.md`
- DECISIONS-LOG.md → `.claude/docs/decisions_log.md`
- SESSION-STATE.md → `.claude/docs/session_state.md`

📦 **Completed Work Archives**
- COMPLETED_IMPROVEMENTS.md → `.claude/summaries/`
- *_COMPLETE.md files → `.claude/summaries/`
- updates.md → `.claude/summaries/`

### Archive (Can be removed or moved to `.claude/archive/`)
🗑️ **Temporary Fix Instructions** (completed tasks)
- FINAL_FIX_INSTRUCTIONS.md
- FIX_CATEGORIES_INSTRUCTIONS.md
- MIGRATION_FIX_INSTRUCTIONS.md
- QUICK_FIX.md
- SIMPLE_FIX.bat
- RUN_THIS_TO_FIX.bat
- README_FIX.txt
- MIGRATION_COMPLETE.txt
- IMAGE_FIX_COMPLETE.txt

🗑️ **Duplicate/Obsolete**
- CLAUDE_CONFIG.md (use CLAUDE.md instead)
- PROJECT-CONTEXT.md (covered in CLAUDE.md)

---

## Action Items

### Phase 1: Organize .claude/
✅ Skills, commands, scripts already organized
⬜ Move session summaries to `.claude/summaries/`
⬜ Move QA/testing docs to `.claude/docs/`
⬜ Create `.claude/archive/` for completed fix instructions

### Phase 2: Clean docs/
⬜ Keep user-facing documentation
⬜ Archive temporary fix files
⬜ Update README.md with new structure

### Phase 3: Update References
⬜ Update CLAUDE.md with new paths
⬜ Update links in documentation

---

## Proposed Final Structure

```
ezzydelivery/
├── docs/                           # User/team documentation
│   ├── api/                        # API guides
│   ├── architecture/               # System design
│   ├── deployment/                 # Production guides
│   ├── development/                # Dev guides
│   └── marketing/                  # Business docs
│
├── .claude/                        # AI assistant config
│   ├── commands/                   # /django, /seo, etc.
│   ├── skills/                     # Expert mode configs
│   ├── scripts/                    # Helper scripts
│   ├── docs/                       # AI-specific docs
│   │   ├── warehouse_testing_todos.md
│   │   ├── qa_todos.md
│   │   └── bugs_and_issues.md
│   ├── summaries/                  # Session summaries
│   │   ├── server-fix-checklist-2026-01-21.md
│   │   └── completed_improvements.md
│   ├── plans/                      # Implementation plans
│   ├── tests/                      # Test scripts
│   └── archive/                    # Completed fix instructions
│
└── CLAUDE.md                       # Main AI instructions
```

---

## Benefits

1. **Clear Separation**
   - `docs/` = human-readable team documentation
   - `.claude/` = AI assistant configuration

2. **Easier Navigation**
   - Developers find guides in `docs/`
   - AI finds automation in `.claude/`

3. **Cleaner Root**
   - No scattered fix scripts
   - No temporary BAT files

4. **Better Maintenance**
   - Archive completed tasks
   - Keep active docs organized

