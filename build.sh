#!/usr/bin/env bash
# Stamp the current git commit into git_hash.h, then run arduino-cli compile.
# Extra arguments go to arduino-cli:
#   ./build.sh                compile
#   ./build.sh --upload       compile + flash
#   ./build.sh -e             compile + export .bin to ./build/
set -euo pipefail
cd "$(dirname "$0")"

hash=$(git describe --always --dirty --abbrev=7 2>/dev/null || echo unknown)
line="#define GIT_HASH \"$hash\""
# Rewrite only on change, so an unchanged commit doesn't force a sketch rebuild
[ "$(cat git_hash.h 2>/dev/null)" = "$line" ] || echo "$line" > git_hash.h

exec arduino-cli compile "$@" .
