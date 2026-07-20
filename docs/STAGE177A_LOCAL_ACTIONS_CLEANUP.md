# Stage177A Local Actions Cleanup

Normal `git` commands cannot remove GitHub Actions artifacts or caches because
those objects are outside the Git repository. This tool calls the GitHub REST
API from your Mac, so no workflow is started and no Actions minutes are used.

## Token

Recommended fine-grained PAT:

- Repository access: `xauusd-trader`
- Repository permission: **Actions — Read and write**

For a private repository, a classic PAT with `repo` scope also works.

## Install

Copy the packaged files into the repository root.

## Preview

```bash
cd ~/Desktop/xauusd-trader

python3 tools/stage177a_local_actions_cleanup.py \
  --purge-caches \
  --delete-gdelt-branch
```

## Execute

```bash
python3 tools/stage177a_local_actions_cleanup.py \
  --execute \
  --confirm DELETE_ALL_XAUUSD_ACTIONS_STORAGE \
  --purge-caches \
  --delete-gdelt-branch
```

The token is requested securely; it is not shown while typing.

Output:

```text
reports/stage177a_local_actions_cleanup_summary.json
```
