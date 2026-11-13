#!/usr/bin/env bash
# Build site/ from course.json and course/ (thin wrapper around engine/build.py; see specs/CONTRACT.md).
# usage (from anywhere): bash engine/build_site.sh [--target artifact|github-pages|file] [--root <repo>] [--stub]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
exec python -I "$here/build.py" "$@"
