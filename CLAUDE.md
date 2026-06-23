# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->


## Build & Test

This is a Home Assistant custom integration (Python, no build step). Run the
pure-logic suite before any deploy or release:

```bash
pip install -r requirements-test.txt
pytest                              # pure-logic suite (stubs HA via tests/conftest.py)

# Optional / CI also runs:
pip install -r requirements-ha-test.txt
pytest tests_ha -o asyncio_mode=auto   # real-HA import + flow-schema guard
```

CI (`.github/workflows/validate.yml`) runs `pytest`, the HA guard, and hassfest
on every push/PR. There is no compile/bundle step for the integration; the
Lovelace card (`www/swelligence-card.js`) is dependency-free vanilla JS.

## Deployment

**Two distinct meanings — confirm which is intended.**

### 1. Deploy to the live Home Assistant (the usual "deploy")

The running HA instance lives at `/appdata/homeassistant/`. Deploying means
syncing the integration source into its `custom_components/` and restarting HA.
Deploy only from a clean, up-to-date `main` that has passed `pytest`.

```bash
cd /workspace/swelligence
git status --porcelain   # must be empty; deploy reflects committed code only
pytest                   # quality gate — green before deploy

# Sync the integration (exclude bytecode; --delete removes files dropped from the repo)
rsync -a --delete --exclude='__pycache__' \
  custom_components/swelligence/ /appdata/homeassistant/custom_components/swelligence/

# Clear stale bytecode so HA can't load an old .pyc
rm -rf /appdata/homeassistant/custom_components/swelligence/__pycache__ \
       /appdata/homeassistant/custom_components/swelligence/providers/__pycache__

# The Lovelace card is separate; only copy when www/swelligence-card.js changed:
# cp www/swelligence-card.js /appdata/homeassistant/www/swelligence-card.js
```

Then **verify**: `diff -rq custom_components/swelligence <dest>` (ignoring
`__pycache__`) should be clean, and `python3 -m py_compile` the deployed `.py`
files.

**The new code does NOT load until Home Assistant restarts** (Settings →
Developer Tools → Restart) or the integration is reloaded (Devices & Services →
Swelligence → ⋮ → Reload). **Do NOT restart HA without explicit confirmation** —
it interrupts a live home-automation system; that step is the user's call. New
config-flow options (e.g. cross-provider confidence toggles) only appear after a
restart, and the user must opt into them in the integration's options.

Notes:
- A file deploy does **not** bump `manifest.json` `version` — that's a release
  concern, kept separate (see below).
- `/appdata/homeassistant/` is its own git repo, so a bad deploy is recoverable
  there (`git diff` / `git checkout` inside that tree).

### 2. Cut a HACS release (version bump + tag)

For HACS consumers, "deploy" instead means bumping `custom_components/swelligence/
manifest.json` `version`, committing, and creating an annotated git tag +
Forgejo release. HACS reads tags/releases. Note: `hacs/action` store-validation
returns 401 against Forgejo (GitHub-only); run it on a GitHub mirror if needed.
Releases are public and hard to unpublish — confirm the version first.

## Architecture Overview

_Add a brief overview of your project architecture_

## Conventions & Patterns

_Add your project-specific conventions here_
