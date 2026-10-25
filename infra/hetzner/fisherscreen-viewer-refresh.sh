#!/bin/bash
# Rebuilds the static dossier viewer from the data repo and switches /var/www/fisher
# to it. Run by fisherscreen-viewer.timer every 5 min as user stef.
# Runbook: docs/superpowers/specs/2026-10-25-dossier-publishing-runbook.md
#
# Layout:  /var/www/fisher -> fisher-builds/current -> fisher-builds/<sha>-<epoch>
# Any failure before the switch exits non-zero and leaves `current` untouched,
# so the previous site stays online.
set -euo pipefail

REPO=/opt/fisherscreen-dossiers
PYTHON=/opt/fisherscreen/.venv/bin/python
BUILDS=/var/www/fisher-builds
KEEP=2   # newest build dirs to keep, besides the live one and legacy-*

cd /opt/fisherscreen   # `python -m app.viewer` needs the code checkout as cwd

git -C "$REPO" pull --ff-only --quiet
sha=$(git -C "$REPO" rev-parse --short=12 HEAD)
# The viewer code lives in the code checkout, so a code update must rebuild too:
# the stamp records data HEAD and code HEAD.
stamp="$sha:$(git -C /opt/fisherscreen rev-parse --short=12 HEAD)"

# Neither changed since the last build and the site is still reachable -> nothing to do.
if [[ -f "$BUILDS/.built-sha" && "$(cat "$BUILDS/.built-sha")" == "$stamp" && -e "$BUILDS/current/index.html" ]]; then
    exit 0
fi

# Every build gets a unique dir name (<sha>-<epoch>), so a rebuild of the same data
# sha can never collide with, or delete, the build `current` points to.
# Build as <name>.tmp and rename, so a half-written dir never has a real name.
name="$sha-$(date +%s)"
rm -rf "$BUILDS"/*.tmp   # leftovers of a failed earlier build
"$PYTHON" -m app.viewer --in "$REPO/Watchlist" --out "$BUILDS/$name.tmp"
mv "$BUILDS/$name.tmp" "$BUILDS/$name"

# Atomic switch: build the new symlink under a temp name, then rename over `current`.
# `mv -T` is a single rename(2), so readers see the old or the new site, never neither.
ln -sfn "$name" "$BUILDS/current.tmp"
mv -T "$BUILDS/current.tmp" "$BUILDS/current"
echo "$stamp" > "$BUILDS/.built-sha"

# Prune: never the live target, `current`, legacy-* or a build in progress; of the
# rest keep the newest $KEEP. Failures here must not fail the run (the switch is done).
live=$(readlink "$BUILDS/current")
cd "$BUILDS"
{ ls -1dt -- */ 2>/dev/null || true; } | sed 's#/$##' \
    | { grep -Ev '^(legacy-.*|current|.*\.tmp)$' || true; } \
    | { grep -Fvx -- "$live" || true; } \
    | tail -n +$((KEEP + 1)) | while read -r old; do
        rm -rf -- "$BUILDS/$old" || echo "prune failed: $old" >&2
    done
echo "viewer switched to $name"
