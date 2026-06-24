# VocaBlurry — MANIFEST

**Routing contract**: scope, navigation, and canonical entry points for the knowledge graph.

**Loaded by**: Agent via MCP at runtime (`read_note("MANIFEST", project="vocablurry")`)  
**Lives in**: Basic Memory project `vocablurry`  
**Audience**: The agent (after CLAUDE.md bootstrap)

---

## Scope

This knowledge graph covers:

- **Architecture**: Two-repo layout (public code, private data), serverless design, cron-driven workflow
- **Scoring system**: 0–5 scale, adaptive weighted sampling, learned vs in-review derivation
- **Telegram integration**: `getUpdates` polling (no webhooks), callback/poll handling
- **GitHub Actions**: Workflow schedules, data repo checkout patterns, UTC timezone gotchas
- **Data management**: JSON state files, scoring persistence, offset tracking

---

## Where to Start

1. **For first-time context**: read_notes("index/overview")
2. **By topic**: search_notes("<topic>") — e.g., "scoring", "two-repo", "workflows", "telegram"
3. **Canonical entry points**: see below

---

## Canonical Entry-Point Notes

Navigate to these notes for deep dives:

- **[[Two-Repo Architecture]]** — why code is public, data is private; how workflows check out and commit back
- **[[Adaptive Scoring System]]** — the 0–5 scale, events that change score, learned/in-review rules, weighted quiz sampling
- **[[Telegram Integration]]** — getUpdates offset tracking, callback deduplication, poll answer handling
- **[[Workflow Schedules]]** — vocab.yml, drain.yml, quiz.yml, health.yml; timezone gotchas; 60-day activity requirement
- **[[Troubleshooting]]** — duplicate updates, missing quiz polls, offset corruption, cron lag
- **[[Local Development]]** — running scripts locally with `./data`, testing without private repo

---

## Quick Reference

| Question | Check |
|----------|-------|
| How does the bot work? | README.md (in repo), then [[Adaptive Scoring System]] |
| Two-repo layout? | [[Two-Repo Architecture]] |
| How do I score a word? | scoring.py (in repo), [[Adaptive Scoring System]] |
| How are workflows scheduled? | .github/workflows/ (in repo), [[Workflow Schedules]] |
| Why did updates duplicate? | [[Troubleshooting]] → offset tracking section |
| How do I test locally? | [[Local Development]] |
| What changed recently? | git log --oneline -5 (in repo) |

---

## Update This Manifest When

- Adding a new workflow or major schedule change
- Changing architecture (data repo layout, scoring rules, Telegram integration)
- Creating new canonical entry-point notes
- Resolving a recurring troubleshooting issue (add to [[Troubleshooting]])
