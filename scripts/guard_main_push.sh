#!/usr/bin/env bash
# pre-push guard: refuse direct pushes to main (use a branch + PR instead).
#
# This repo is private on a GitHub Free account, which has no server-side branch
# protection (see README "Branches and merging"). This guard only covers this
# machine; it is a convenience, not a security boundary.
set -euo pipefail

# pre-commit exports the remote ref being pushed during the pre-push stage.
if [ "${PRE_COMMIT_REMOTE_BRANCH:-}" = "refs/heads/main" ]; then
  echo "direct push to main is refused: push a branch and open a PR instead." >&2
  exit 1
fi
