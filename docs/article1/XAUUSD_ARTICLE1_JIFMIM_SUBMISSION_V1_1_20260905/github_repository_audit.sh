#!/usr/bin/env bash
set -euo pipefail

repo_path="${1:-.}"
cd "$repo_path"

git rev-parse --is-inside-work-tree >/dev/null
branch_name="$(git branch --show-current)"
if [[ -z "$branch_name" ]]; then
  echo "ERROR: detached HEAD; check out the intended branch before auditing." >&2
  exit 2
fi

git fetch --prune origin

remote_ref="origin/$branch_name"
git rev-parse --verify "$remote_ref" >/dev/null

audit_tmp="$(mktemp -d)"
trap 'rm -r "$audit_tmp"' EXIT

git ls-files | LC_ALL=C sort > "$audit_tmp/local_tracked.txt"
git ls-tree -r --name-only "$remote_ref" | LC_ALL=C sort > "$audit_tmp/remote_tracked.txt"

echo "BRANCH=$branch_name"
echo "LOCAL_HEAD=$(git rev-parse HEAD)"
echo "REMOTE_HEAD=$(git rev-parse "$remote_ref")"
echo "AHEAD_BEHIND=$(git rev-list --left-right --count "$remote_ref...HEAD")"

echo
echo "LOCAL_TRACKED_NOT_ON_REMOTE"
comm -23 "$audit_tmp/local_tracked.txt" "$audit_tmp/remote_tracked.txt" || true

echo
echo "REMOTE_TRACKED_NOT_LOCAL"
comm -13 "$audit_tmp/local_tracked.txt" "$audit_tmp/remote_tracked.txt" || true

echo
echo "TRACKED_CONTENT_DIFFERENCES"
git diff --name-status "$remote_ref" --

echo
echo "UNTRACKED_NOT_IGNORED"
git ls-files --others --exclude-standard

echo
echo "WORKTREE_STATUS"
git status --short

echo
echo "ARTICLE_PACKAGE_TRACKING_STATUS"
git status --short -- docs article manuscripts papers 2>/dev/null || true

echo
echo "AUDIT_COMPLETE"
