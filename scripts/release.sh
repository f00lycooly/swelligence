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
FORCED=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --no-push) PUSH=0 ;;
    --strict)  STRICT=1 ;;
    --as)      FORCED="${2:-}"; shift ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

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

# Prepend a CHANGELOG section from the commit subjects in range.
date="$(git log -1 --format=%cs HEAD)"
{
  echo "## v$next — $date"
  echo
  git log --format='- %s' $range 2>/dev/null | grep -vE '^- chore\(release\):' || true
  echo
  if [[ -f "$CHANGELOG" ]]; then echo; cat "$CHANGELOG"; fi
} > "$CHANGELOG.tmp"
if [[ ! -f "$CHANGELOG" ]]; then
  printf '# Changelog\n\nAll notable changes per release. Versions follow semver; tags are `vX.Y.Z`.\n\n' \
    | cat - "$CHANGELOG.tmp" > "$CHANGELOG"
else
  mv "$CHANGELOG.tmp" "$CHANGELOG"
fi
rm -f "$CHANGELOG.tmp"

git add "$MANIFEST" "$CHANGELOG"
git commit -q -m "chore(release): v$next"
git tag -a "v$next" -m "v$next"
echo "committed + tagged v$next"

if [[ "$PUSH" == "1" ]]; then
  git push "$REMOTE" HEAD
  git push "$REMOTE" "v$next"
  echo "pushed to $REMOTE; the Forgejo push mirror will carry v$next to GitHub,"
  echo "where release.yml publishes the GitHub Release HACS reads."
else
  echo "local only (--no-push). Push with: git push $REMOTE HEAD && git push $REMOTE v$next"
fi
