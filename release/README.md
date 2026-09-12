# Release tooling

Cross-repository release tooling for the krabka-io Rust repositories.

| File | What it does |
| ---- | ------------ |
| [`check-publish-allowlist.sh`](check-publish-allowlist.sh) | Checks that a workspace publishes exactly the crates its allowlist names, and that `release-plz.toml` agrees with `cargo metadata` |
| [`publish-dryrun.sh`](publish-dryrun.sh) | Runs format, clippy, test, deny, `cargo publish --dry-run` and rustdoc before a release |
| [`bump-crate-versions.py`](bump-crate-versions.py) | Rewrites the `krabka-*` versions in `Cargo.toml` and `Cargo.lock` to one target version |
| [`bootstrap-publish.py`](bootstrap-publish.py) | Publishes the crates crates.io does not hold yet, in dependency order, and waits out the rate limit |
| [`release-plz.toml`](release-plz.toml) | The shared release-plz workspace defaults |
| [`release-plz-changelog.toml`](release-plz-changelog.toml) | The shared changelog template and commit parsers |

## The open question: copy or fetch

`robot-head/crabka#1071` records the question and does not answer it. This is
the answer, and every repository follows it.

**Scripts are fetched. Configuration is copied.**

The split follows from how each kind of file is read:

- A script is read by CI at run time, so CI can fetch it. One copy of the
  script means one place to fix a bug in it.
- `release-plz` reads its configuration from the root of the repository it
  releases. It has no way to fetch a remote file. So the two `release-plz`
  TOML files have to be copied into each repository.

### Scripts: call the reusable workflow

[`.github/workflows/release-checks.yml`](../.github/workflows/release-checks.yml)
in this repository is a `workflow_call` workflow. Add this job to the caller's
`ci.yml`:

```yaml
jobs:
  release-checks:
    uses: krabka-io/tooling/.github/workflows/release-checks.yml@main
    with:
      rust-toolchain: "1.97.0"
```

The workflow checks out the calling repository at the calling commit, checks
out this repository beside it, and runs `html-root-url.sh` and
`check-publish-allowlist.sh` against the caller's tree.

Pin `@main` to a tag once this repository has one. A release gate that floats
on `main` can go red because of a commit here rather than a commit in the
repository under test.

While `krabka-io/tooling` is **private**, the second checkout needs a token
that can read it. Either grant Actions access (repository settings, Actions,
"Access", accessible from repositories in the krabka-io organization) and make
the repository public, or pass a read-only PAT:

```yaml
    secrets:
      tooling-token: ${{ secrets.TOOLING_READ_TOKEN }}
```

`publish-dryrun.sh`, `bump-crate-versions.py` and `bootstrap-publish.py` are
run by a person, not by CI. Clone this repository once and run them from the
root of the repository you release:

```sh
git clone --depth 1 https://github.com/krabka-io/tooling ~/src/krabka-tooling
cd ~/src/krabka-broker
~/src/krabka-tooling/release/publish-dryrun.sh
```

Every script acts on the git repository of the working directory, never on the
one that holds the script.

### Configuration: copy both TOML files

Copy `release-plz.toml` and `release-plz-changelog.toml` into the root of the
repository, then add one `[[package]]` entry per crate in that workspace.

`release-plz-changelog.toml` is the file that is shared **without a change**.
It holds only the changelog body template and the commit parsers, and those are
the same in every repository. `release-plz.toml` is shared only down to its
`[workspace]` table. The monorepo version of it also carried a
`publish`/`release` entry for each of about ninety crates. Those crates now sit
in twelve repositories, so that table is repository-specific and this copy does
not hold it.

## The allowlist file

`check-publish-allowlist.sh` and `publish-dryrun.sh` both read
`publish-allowlist.txt` from the root of the repository under test. It holds
one crate name per line, and `#` starts a comment:

```
# Public: useful as standalone libraries outside this repository.
krabka-protocol
krabka-compression
krabka-ids
```

A crate that is not in the file must set `publish = false` in its
`Cargo.toml`. The check fails when the two disagree, and it fails again when
`release-plz.toml` does not match either of them. That is the point of it: the
three statements of "which crates does this repository publish" cannot drift
apart silently.
