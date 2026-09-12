#!/usr/bin/env bash
# Run every publish-readiness check for a krabka-io Rust workspace.
#
# Run it from the root of the repository under test:
#
#   /path/to/tooling/release/publish-dryrun.sh [crate ...]
#
# Each named crate gets a `cargo publish --dry-run`. With no crate named, the
# script reads the crate names from `publish-allowlist.txt` in the working
# directory, the same file `check-publish-allowlist.sh` reads.
#
# A crate that depends on a sibling crate which is not yet on crates.io cannot
# pass `cargo publish --dry-run`, because the dry run resolves the dependency
# against the registry. Publish the dependency first, or drop the dependent
# crate from the argument list for that run.
set -euo pipefail

crates=("$@")
if [ "${#crates[@]}" -eq 0 ]; then
    if [ ! -f publish-allowlist.txt ]; then
        echo "no crate named and no publish-allowlist.txt in $(pwd)" >&2
        exit 1
    fi
    mapfile -t crates < <(sed 's/#.*//' publish-allowlist.txt | awk 'NF')
fi

echo "==> cargo fmt --check"
cargo fmt --check

echo "==> cargo clippy --workspace --all-targets -- -D warnings"
cargo clippy --workspace --all-targets -- -D warnings

echo "==> cargo test --workspace"
cargo test --workspace

echo "==> cargo deny check"
cargo deny check

for crate in "${crates[@]}"; do
    echo "==> cargo publish --dry-run for ${crate}"
    cargo publish -p "${crate}" --dry-run --allow-dirty
done

echo "==> rustdoc with --cfg docsrs"
RUSTDOCFLAGS="--cfg docsrs -D warnings" \
    cargo doc --workspace --no-deps --all-features

echo "==> All publish-readiness checks passed."
