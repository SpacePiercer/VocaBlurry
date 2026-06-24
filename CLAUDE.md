# VocaBlurry — CLAUDE.md

**Bootstrap instructions for Claude Code harness. Read MANIFEST.md for actual knowledge routing.**

---

On startup, load the knowledge graph:

```bash
/mcp  # verify Basic Memory MCP is available
```

Then read the project MANIFEST:

```
read_note("MANIFEST", project="vocablurry")
```

Or via memory search if project is not yet created:

1. `list_memory_projects()` — find vocablurry project in Basic Memory
2. `search_notes("vocablurry MANIFEST")` — search for entry point
3. `read_note("MANIFEST", project="vocablurry")` — load routing contract

The MANIFEST contains scope, navigation rules, and canonical entry-point notes.

---

**In this repo only**: README.md (how it works), `.github/workflows/` (schedules), `scoring.py` (scoring logic).

For decisions, context, and knowledge structure → **read MANIFEST.md**.

---

## Startup Sequence — Git Hygiene Check

Before starting any task, run:

```bash
git status                           # uncommitted files
git log --oneline origin/main..HEAD  # commits not yet in main
git branch -r --no-merged main       # remote branches not yet merged
```

If uncommitted changes or unmerged branches exist:
- **Determine which branch each change belongs to** (feature work vs. project-wide config vs. docs).
- If changes are on the wrong branch, move them to a purpose-appropriate branch before proceeding.
- Report findings to the user before starting the requested task.
