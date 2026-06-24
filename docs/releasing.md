# Releasing Swelligence (HACS)

Swelligence is developed on **Forgejo** (primary) but distributed through **HACS**,
which only integrates with **GitHub**. So GitHub is a one-way **push mirror** of
Forgejo and acts as the *release surface* HACS reads. You never develop on GitHub.

```
 Forgejo (origin, primary)  ──push mirror──▶  GitHub (mirror, HACS-facing)
   you commit & tag here                       release.yml publishes the Release
                                               HACS reads the latest vX.Y.Z
```

Why this shape: HACS resolves versions from GitHub **Releases**; `hacs/action`
validation only works against the GitHub API (401 on Forgejo). Keeping Forgejo
primary honours the org rule; a tag-triggered Action (not release-please) keeps
the mirror strictly one-way so nothing has to be written back from GitHub.

---

## One-time setup (infra — `swelligence-ckl.2`)

1. **Create the GitHub repo** `github.com/f00lycooly/swelligence` (empty — no
   README/license; the mirror provides everything).
2. **Add a Forgejo push mirror** → in the Forgejo repo: *Settings → Repository →
   Mirror Settings → Add Push Mirror*:
   - Git Remote URL: `https://github.com/f00lycooly/swelligence.git`
   - Authorization: a GitHub **PAT** with `repo` + `workflow` scopes
   - **Leave “Sync when new commits are pushed” UNticked** — this mirror is
     **sync-on-release**, not sync-on-commit. `scripts/release.sh` forces a
     one-shot sync at release time (via the `push_mirrors-sync` API), so GitHub
     only gets pushed when a release is cut. Keep a periodic interval (e.g. 8h)
     as a harmless backstop.
   Push mirrors propagate **branches *and* tags**.
3. **Enable GitHub Actions** on the mirror (Actions tab → enable workflows). The
   mirrored `.github/workflows/release.yml` runs there on tag pushes.
4. **Verify**: push any commit to Forgejo `origin` and confirm it appears on
   GitHub within the sync window.

> `validate.yml`’s `hassfest` job is pinned to the self-hosted `tinkernet-host`
> runner and is **skipped on GitHub** (guarded by `github.server_url`), so the
> mirror won’t leave it queued forever. `release.yml` runs hassfest on
> GitHub-hosted `ubuntu-latest` instead.

---

## Cutting a release (ongoing — `swelligence-ckl.3` for the first one)

From a clean, green `main`:

```bash
git checkout main && git pull --rebase
pytest                       # gate: must be green
scripts/release.sh --dry-run # preview the inferred version + included commits
scripts/release.sh           # bump manifest + CHANGELOG, commit, tag, push to origin
```

**First release** — there is no prior tag and `manifest.json` is already at
`0.1.0`, so tag that version as-is rather than letting the inference bump it:

```bash
scripts/release.sh --as 0.1.0
```

`scripts/release.sh` infers the next semver from the **conventional commits**
since the last `v*` tag (0.x-aware: pre-1.0 a breaking change bumps *minor*, a
`feat` bumps *patch*), bumps `custom_components/swelligence/manifest.json`,
prepends a `CHANGELOG.md` section, commits `chore(release): vX.Y.Z`, creates an
annotated `vX.Y.Z` tag, pushes to Forgejo `origin`, **and forces a one-shot
push-mirror sync so the tag reaches GitHub immediately**. Overrides:
`--as X.Y.Z` (explicit version), `--no-push` (local only),
`--no-mirror-sync` (push but don't force the mirror), `--strict` (abort if
no release-worthy commits).

Then the pipeline runs itself:

1. The forced push-mirror sync carries the tag to GitHub (no waiting on the 8h
   interval, since the mirror is sync-on-release).
2. `release.yml` fires on the `v*` tag: asserts **tag == manifest version**, runs
   the tests + HA guard + hassfest + **`hacs/action`**, then publishes a GitHub
   **Release** with auto-generated notes.
3. HACS sees the new Release and offers it to users. Because `hacs.json` sets
   `hide_default_branch: true`, HACS only ever offers tagged releases, never raw
   `main`.

### Manual fallback (broken mirror / Actions disabled)

```bash
# push the tag straight to GitHub and let release.yml run there
git push github vX.Y.Z         # if a `github` remote is configured
# or create the Release by hand from the tag in the GitHub UI
```

---

## Versioning rules

- `manifest.json` `version` is the single source of truth and **must equal** the
  tag (`vX.Y.Z` → `X.Y.Z`); `release.yml` fails the release if they diverge.
- Semantic versioning. Pre-1.0 (`0.y.z`): breaking → `0.(y+1).0`, feat/fix →
  `0.y.(z+1)`. At 1.0+: standard major/minor/patch.
- A file-sync deploy to the live HA instance is **not** a release — it does not
  touch `version`. See `CLAUDE.md` → Deployment for the two distinct meanings.
- Releases are public and hard to unpublish — confirm the version before pushing
  the tag.
