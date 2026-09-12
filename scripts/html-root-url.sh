#!/usr/bin/env bash
# Keep every crate's `#![doc(html_root_url = "https://docs.rs/<crate>/<ver>")]`
# in sync with the workspace version. `html_root_url` cannot use env!/concat!,
# so it must be rewritten on each version bump. This script enforces that, and
# can do the rewrite.
#
# Run it from the root of the repository under test. The script acts on the git
# repository of the working directory, not on the repository that holds it.
#
#   /path/to/tooling/scripts/html-root-url.sh         # check; non-zero exit if any are stale (CI gate)
#   /path/to/tooling/scripts/html-root-url.sh --fix   # rewrite all to the current workspace version
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

ver=$(grep -m1 '^version = ' Cargo.toml | sed -E 's/.*"([^"]+)".*/\1/')
mode=${1:-check}
rc=0

while IFS=: read -r file _line _rest; do
    have=$(sed -nE 's|.*html_root_url = "https://docs\.rs/[a-z0-9_-]+/([0-9]+\.[0-9]+\.[0-9]+)".*|\1|p' "$file" | head -1)
    [ "$have" = "$ver" ] && continue
    if [ "$mode" = "--fix" ]; then
        sed -i.bak -E "s|(html_root_url = \"https://docs\.rs/[a-z0-9_-]+)/[0-9]+\.[0-9]+\.[0-9]+\"|\1/${ver}\"|" "$file"
        rm -f "$file.bak"
        echo "fixed $file -> $ver"
    else
        echo "::error file=$file::html_root_url is $have, expected workspace version $ver"
        rc=1
    fi
done < <(grep -rln 'html_root_url' crates --include='*.rs' | sed 's/$/:0:/')

if [ "$rc" -ne 0 ]; then
    echo "html_root_url out of sync with workspace version $ver — run: html-root-url.sh --fix" >&2
fi
exit "$rc"
