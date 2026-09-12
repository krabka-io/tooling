#!/usr/bin/env bash
# List the hardcoded runtime values in a krabka-io Rust workspace: constants,
# durations, capacities, channel sizes, timeouts and the like. The output is
# the candidate set for a configuration audit. See the configuration-audit
# document of the repository under test.
#
# Run it from the root of that repository. The script acts on the git
# repository of the working directory, not on the repository that holds it.
# It needs ripgrep.
set -euo pipefail
export LC_ALL=C

root=$(git rev-parse --show-toplevel)
cd "$root"

{
  rg -n \
    --glob '*.rs' \
    --glob '!**/tests/**' \
    --glob '!**/benches/**' \
    --glob '!**/*_model.rs' \
    --glob '!**/test_*.rs' \
    '(^[[:space:]]*(pub([[:space:]]*\([^)]*\))?[[:space:]]+)?const[[:space:]]+[A-Z][A-Z0-9_]*|Duration::from_(secs|millis|micros|nanos|mins)\([0-9_]+\)|with_capacity\([0-9_]+\)|(channel|sync_channel)(::<[^>]+>)?\([0-9][0-9_]*\)|(Semaphore::new|buffered|buffer_unordered)\([0-9][0-9_]*\)|[A-Za-z_][A-Za-z0-9_]*(channel|semaphore|buffer|queue|limit|timeout|interval|backoff|capacity|delay|deadline|max_bytes|min_bytes|poll|tick)[A-Za-z0-9_]*\([0-9][0-9_]*\)|[A-Za-z_][A-Za-z0-9_]*(channel|semaphore|buffer|queue|limit|timeout|interval|backoff|capacity|batch|delay|deadline|max_bytes|min_bytes|poll|tick)[A-Za-z0-9_]*[[:space:]]*[:=][[:space:]]*[0-9][0-9_]*|(channel|semaphore|buffer|queue|limit|timeout|interval|backoff|capacity|batch|delay|deadline|max_bytes|min_bytes|poll|tick)[A-Za-z0-9_]*[[:space:]]*[:=][[:space:]]*[0-9][0-9_]*|\.(min|max)\([1-9][0-9_]*\))' \
    crates
  # The broker share-partition manager holds a long table of bare numeric
  # literals that the pattern above cannot reach. Only krabka-broker has the
  # file, so every other repository skips this second pass.
  manager=crates/broker/src/share_partition/manager.rs
  if [ -f "$manager" ]; then
    rg -nH '^[[:space:]]+[0-9][0-9_]*,?[[:space:]]*$' "$manager" || true
  fi
} | sort -u
