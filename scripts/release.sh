#!/usr/bin/env bash
# Release helper — Forgejo-primary, GitHub-mirror, tag-triggered model.
#
# Infers the next semantic version from the conventional commits since the last
# `v*` tag, bumps `custom_components/swelligence/manifest.json`, updates
# CHANGELOG.md, commits a `chore(release): vX.Y.Z`, creates an annotated tag,
# and (unless --no-push) pushes both to the Forgejo `origin`. The Forgejo push
# mirror then carries the tag to GitHub, where `.github/workflows/release.yml`
# validates it and publishes the GitHub Release that HACS consumes.
#
# Usage:
#   scripts/release.sh                 # infer bump, apply, push to origin
#   scripts/release.sh --dry-run       # show the computed version, change nothing
#   scripts/release.sh --as 0.4.0      # force an explicit version
#   scripts/release.sh --no-push       # bump + commit + tag locally, don't push
#   scripts/release.sh --no-mirror-sync# push, but don't force the GitHub mirror sync
#
# Mirror model: the Forgejo push mirror is sync-on-release (NOT sync-on-commit),
# so after pushing the tag this script forces a one-shot mirror sync via the
# Forgejo API (push_mirrors-sync) — that is the ONLY time the GitHub mirror is
# pushed on purpose, and it's what makes release.yml fire promptly.
#
# Bump rules (0.x-aware — pre-1.0, a breaking change bumps MINOR, not MAJOR):
#   * any `feat!:` / `fix!:` / `BREAKING CHANGE` -> minor (pre-1.0) / major (>=1.0)
#   * any `feat:`                                 -> minor (>=1.0) / patch (pre-1.0)
#   * any `fix:` / `perf:`                        -> patch
#   * docs/chore/refactor/test/ci/build only      -> patch (still a release-worthy
#                                                    snapshot; abort with --strict)
set -euo pipefail

MANIFEST="custom_components/swelligence/manifest.json"
CHANGELOG="CHANGELOG.md"
REMOTE="origin"   # Forgejo primary; the push mirror fans out to GitHub

DRY_RUN=0
PUSH=1
STRICT=0
MIRROR_SYNC=1
FORCED=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)         DRY_RUN=1 ;;
    --no-push)         PUSH=0 ;;
    --no-mirror-sync)  MIRROR_SYNC=0 ;;
    --strict)          STRICT=1 ;;
    --as)              FORCED="${2:-}"; shift ;;
    -h|--help) sed -n '2,34p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

# Force a one-shot sync of the Forgejo push mirror so the freshly-pushed tag
# reaches GitHub now (the mirror is sync-on-release, not sync-on-commit). Owner/
# repo + host are derived from the origin URL; the token comes from git's
# credential store. Best-effort: a failure here never fails the release — the
# tag is already on Forgejo, and the periodic interval / a manual "Synchronize
# Now" are backstops.
trigger_mirror_sync() {
  local url host path owner repo token code
  url="$(git remote get-url "$REMOTE")"
  url="${url#*://}"; url="${url#*@}"        # strip scheme + any embedded creds
  host="${url%%/*}"
  path="${url#*/}"; path="${path%.git}"
  owner="${path%%/*}"; repo="${path##*/}"
  if [[ "$host" != *.* || -z "$owner" || -z "$repo" || "$owner" == "$path" ]]; then
    echo "warn: couldn't parse Forgejo owner/repo from $REMOTE; sync the mirror manually." >&2
    return 0
  fi
  token="$(printf 'protocol=https\nhost=%s\n\n' "$host" | git credential fill 2>/dev/null | sed -n 's/^password=//p')"
  if [[ -z "$token" ]]; then
    echo "warn: no stored credential for $host; sync the mirror manually (Forgejo -> Synchronize Now)." >&2
    return 0
  fi
  code="$(curl -s -o /dev/null -w '%{http_code}' -X POST \
    -H "Authorization: token $token" \
    "https://$host/api/v1/repos/$owner/$repo/push_mirrors-sync")"
  if [[ "$code" == "200" || "$code" == "204" ]]; then
    echo "forced Forgejo push-mirror sync -> GitHub (HTTP $code)."
  else
    echo "warn: mirror sync trigger returned HTTP $code; use Forgejo 'Synchronize Now' if the tag doesn't appear." >&2
  fi
}

cd "$(git rev-parse --show-toplevel)"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "error: working tree has uncommitted changes; commit or stash first." >&2
  exit 1
fi

current="$(python3 -c "import json;print(json.load(open('$MANIFEST'))['version'])")"
last_tag="$(git describe --tags --match 'v*' --abbrev=0 2>/dev/null || echo '')"
range="${last_tag:+$last_tag..HEAD}"

if [[ -n "$FORCED" ]]; then
  next="$FORCED"
else
  subjects="$(git log --format='%s%n%b' $range 2>/dev/null || git log --format='%s%n%b')"
  bump="patch"
  if grep -qiE '(^|\n)(feat|fix|refactor|perf)(\([^)]*\))?!:|BREAKING[ -]CHANGE' <<<"$subjects"; then
    bump="breaking"
  elif grep -qE '(^|\n)feat(\([^)]*\))?:' <<<"$subjects"; then
    bump="feat"
  elif grep -qE '(^|\n)(fix|perf)(\([^)]*\))?:' <<<"$subjects"; then
    bump="patch"
  elif [[ "$STRICT" == "1" ]]; then
    echo "error: no feat/fix/perf/breaking commits since ${last_tag:-repo start}; nothing to release (--strict)." >&2
    exit 1
  fi

  IFS=. read -r MAJ MIN PAT <<<"$current"
  if [[ "$MAJ" == "0" ]]; then            # pre-1.0: breaking->minor, feat->patch
    case "$bump" in
      breaking) MIN=$((MIN+1)); PAT=0 ;;
      feat|patch) PAT=$((PAT+1)) ;;
    esac
  else                                    # >=1.0: standard semver
    case "$bump" in
      breaking) MAJ=$((MAJ+1)); MIN=0; PAT=0 ;;
      feat)     MIN=$((MIN+1)); PAT=0 ;;
      patch)    PAT=$((PAT+1)) ;;
    esac
  fi
  next="${MAJ}.${MIN}.${PAT}"
fi

echo "current: $current   last tag: ${last_tag:-<none>}   ->  next: $next"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "(dry-run) commits considered:"
  git log --oneline $range 2>/dev/null || true
  exit 0
fi

if git rev-parse "v$next" >/dev/null 2>&1; then
  echo "error: tag v$next already exists." >&2
  exit 1
fi

# Bump manifest version (preserve key order + 2-space indent + trailing newline).
python3 - "$MANIFEST" "$next" <<'PY'
import json, sys
path, ver = sys.argv[1], sys.argv[2]
data = json.load(open(path))
data["version"] = ver
with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

# Insert a new CHANGELOG section *below the pinned header* (not above the whole
# file — that buries the title between versions). Layout stays:
#   # Changelog \n <intro> \n ## vNEW \n ... \n ## vOLD \n ...
# release.yml extracts a single "## vX.Y.Z" section as the GitHub Release body
# (which HACS shows), so the header must never land inside a version section.
date="$(git log -1 --format=%cs HEAD)"
header=$'# Changelog\n\nAll notable changes per release. Versions follow semver; tags are `vX.Y.Z`.'
section="$(
  echo "## v$next — $date"
  echo
  # User-facing summary: drop release/bead bookkeeping and merge commits.
  git log --format='- %s' $range 2>/dev/null \
    | grep -vE '^- (chore\(release\)|chore\(beads\)|Merge (pull request|branch|remote))' \
    || true
)"
# Existing version sections only (from the first "## v" onward); drops any old
# header so it isn't duplicated, and self-heals a previously-misordered file.
existing=""
[[ -f "$CHANGELOG" ]] && existing="$(awk '/^## v[0-9]/{f=1} f{print}' "$CHANGELOG")"
{
  printf '%s\n\n' "$header"
  printf '%s\n' "$section"
  [[ -n "$existing" ]] && { printf '\n'; printf '%s\n' "$existing"; }
} > "$CHANGELOG"

git add "$MANIFEST" "$CHANGELOG"
git commit -q -m "chore(release): v$next"
git tag -a "v$next" -m "v$next"
echo "committed + tagged v$next"

if [[ "$PUSH" == "1" ]]; then
  git push "$REMOTE" HEAD
  git push "$REMOTE" "v$next"
  echo "pushed v$next to $REMOTE."
  if [[ "$MIRROR_SYNC" == "1" ]]; then
    trigger_mirror_sync
  else
    echo "(--no-mirror-sync) GitHub won't see v$next until the next mirror sync."
  fi
  echo "GitHub release.yml then validates the tag and publishes the Release HACS reads."
else
  echo "local only (--no-push). Push with: git push $REMOTE HEAD && git push $REMOTE v$next"
  echo "(then sync the mirror: Forgejo -> Synchronize Now, or re-run with push enabled.)"
fi
