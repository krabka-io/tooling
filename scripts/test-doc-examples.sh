#!/usr/bin/env bash
# Build and run every documented client-streams example, then check that the
# website snippets match their source (doc-drift guard).
#
# Run it from the root of the repository that owns the `krabka-client-streams`
# and `krabka-docgen` crates and the `website/` tree.
set -euo pipefail

echo "==> building all client-streams examples"
cargo build -p krabka-client-streams --examples --features polars,arrow

echo "==> running self-asserting examples"
cargo run -p krabka-client-streams --example format_json
cargo run -p krabka-client-streams --example format_arrow --features arrow
cargo run -p krabka-client-streams --example format_dsl
cargo run -p krabka-client-streams --example format_pipeline --features polars,arrow

echo "==> checking documentation snippets are in sync"
cargo run -p krabka-docgen -- snippets
if ! git diff --quiet -- website/content; then
  echo "ERROR: website snippets are stale. Run: cargo run -p krabka-docgen -- snippets" >&2
  git --no-pager diff -- website/content >&2
  exit 1
fi

echo "==> doc examples OK"
