# tooling

Shared build and release inputs for the krabka-io repositories.

Krabka was one monorepo. It is now about a dozen repositories. Shared release
tools, container recipes, documentation tools, and the Helm chart signing key
live here. Multiple component repositories use these files.

This repository holds no Rust. There is no `Cargo.toml`, no Bazel workspace and
no toolchain file. Nothing here is built. It also holds one AXL module, the
shared `rustdoc-site` task of the Aspect CLI, and a Pages upload action.

## Directories

| Directory | What is in it | Who uses it |
| --------- | ------------- | ----------- |
| [`release/`](release/README.md) | Publish gate, version bumper, crates.io bootstrap, and the release-plz templates | Every krabka-io Rust repository |
| [`packaging/`](packaging/README.md) | The Creusot verifier toolchain recipe and a local-binary Dockerfile | krabka-broker, local runs |
| [`aspect/`](aspect/) | The AXL module that exports the `rustdoc-site` task, and the Krabka theme of the pages it publishes | Every krabka-io Rust repository that publishes API documentation |
| [`actions/upload-rustdoc-pages/`](actions/upload-rustdoc-pages/) | Filtered Pages packaging and final archive validation | Every krabka-io Rust repository that publishes API documentation |
| [`actions/gate/`](actions/gate/) | One required CI check for pull requests and merge groups | Every krabka-io repository |
| [`scripts/`](scripts/) | Repository-agnostic check scripts | Named per script below |
| [`charts/`](charts/README.md) | The Helm chart signing public key | `krabka-operator`, `krabka-rebalancer`, `krabka-schema-registry` |

## Scripts

Each script acts on the git repository of the working directory, not on the
repository that holds the script. Run them from the root of the repository you
want to check.

| Script | What it does | Who uses it |
| ------ | ------------ | ----------- |
| [`scripts/html-root-url.sh`](scripts/html-root-url.sh) | Checks that every crate's `html_root_url` names the workspace version, and can fix them | Every repository that publishes crates |
| [`scripts/audit-runtime-values.sh`](scripts/audit-runtime-values.sh) | Lists the hardcoded constants, timeouts and capacities that a configuration audit reviews | `krabka-broker`, and any repository running the same audit |

`scripts/html-root-url.sh` also runs from the shared CI workflow. See
[`release/README.md`](release/README.md).

## How a repository consumes this one

CI **fetches** the scripts. It does not copy them. Add one job to the caller's
`ci.yml`:

```yaml
jobs:
  release-checks:
    uses: krabka-io/tooling/.github/workflows/release-checks.yml@main
    with:
      rust-toolchain: "1.97.0"
```

Configuration is the exception. `release-plz` reads its two TOML files from the
root of the repository it releases and cannot fetch them, so those are copied.
[`release/README.md`](release/README.md) states the whole contract.

## How a repository consumes the CI gate

Run CI on `pull_request`, `merge_group` and pushes to the default branch.
Add a job named `gate`. List every required CI job in its `needs` field.
Pin the action to a reviewed commit:

```yaml
  gate:
    name: gate
    if: always()
    needs: [build, test]
    runs-on: ubuntu-26.04
    steps:
      - uses: krabka-io/tooling/actions/gate@COMMIT_SHA
        with:
          results: ${{ toJSON(needs) }}
          # Set only for lanes that have a job-level condition.
          allow-skipped: nightly
```

Require the `gate` check in the repository rules. Enable the merge queue.
The action rejects failed, cancelled and unknown job results. It permits
skipped jobs only for IDs in `allow-skipped`, a comma-separated list. Leave
this input empty when every job must run. At least one required job must succeed.
The `if: always()` condition makes the gate report failures in its dependencies.

## How a repository consumes the Pages upload action

Keep the existing documentation build and site assembly steps. Replace the
Pages upload step with `actions/upload-rustdoc-pages` from this repository.
Pin it to a reviewed commit. Do not copy its files into consumers.

See [the action guide](actions/upload-rustdoc-pages/README.md) for the input,
file selection rules, required tools, and deployment job setup. The action pin
is separate from the AXL module pin.

## How a repository consumes the AXL module

The root `MODULE.aspect` of this repository is an AXL module. Each release
`vX.Y.Z` of this repository carries the module as the asset
`tooling-X.Y.Z.tar.gz`. A consumer adds it to its own `MODULE.aspect` as an
archive dependency:

```python
axl_archive_dep(
    name = "krabka_tooling",
    urls = ["https://github.com/krabka-io/tooling/releases/download/vX.Y.Z/tooling-X.Y.Z.tar.gz"],
    integrity = "sha512-...",
    strip_prefix = "tooling-X.Y.Z",
    auto_use_tasks = True,
    dev = True,
)
```

`auto_use_tasks = True` registers the tasks that the module declares. The
Aspect CLI accepts only `.tar.gz` archives. It does not resolve dependencies of
a module, so the module holds everything it needs.

Pin a release asset. Do not pin `github.com/krabka-io/tooling/archive/<ref>`.
A Claude Code cloud sandbox that does not have this repository attached gets
403 for that URL, and the Aspect CLI then fails before it runs any task. The
same sandbox can download a release asset.

The module exports only `rustdoc-site`. The `axl-tests` task in `.aspect/`
serves this repository and is not exported. Every consumer defines its own
`axl-tests` task, and a second task with that name would break it.

### Cutting a release

The [`release`](.github/workflows/release.yml) workflow publishes the asset.
CI runs the same archive validation for pull requests and merge groups before
the required `gate` check. Only the tag publishing job has write permission.
A maintainer pushes a tag `vX.Y.Z` on a commit of `main`:

```
git tag vX.Y.Z origin/main
git push origin vX.Y.Z
```

The workflow builds `tooling-X.Y.Z.tar.gz` from `MODULE.aspect`, `aspect/`,
`LICENSE` and `NOTICE`, under the prefix `tooling-X.Y.Z/`. It checks that every
file the module loads is in the archive. It then creates the release with the
archive and `tooling-X.Y.Z.tar.gz.sha512`, which holds the `integrity` value.
The release notes hold the `axl_archive_dep` block to paste into a consumer.

### Moving a consumer to a newer release

1. Pick a release of this repository.
2. Copy the `axl_archive_dep` block from its release notes into the
   `MODULE.aspect` of the consumer.
3. To check the digest, download the asset and compute it:

   ```
   echo "sha512-$(openssl dgst -sha512 -binary tooling-X.Y.Z.tar.gz | base64 -w0)"
   ```

A consumer must not keep its own copy of `rustdoc_site.axl`, `theme.axl`,
`testing.axl` or `repo.axl`. A fix goes in this repository, and each consumer
then moves to it.

### Theme

`aspect/theme.axl` holds the Krabka theme. The `rustdoc-site` task adds it to
the rustdoc output of each crate. It prepends a font import to
`static.files/rustdoc-<hash>.css`, appends an override stylesheet, and replaces
`static.files/favicon-<hash>.svg` with the Krabka logo. The override gives the
light, dark and ayu themes of rustdoc one dark palette, so the theme picker
cannot show a page that clashes with krabka.io. The task does not change any
HTML file. `landing_style()` styles the landing page and the redirect pages.

To run the unit tests of the module, run `aspect axl-tests` at the root of this
repository.

## What is not here

- `packaging/base.apko.yaml` and its lockfile. `krabka-io/krabka-broker` owns
  the runtime base layer.
- Anything a single component owns. A build script that names one component's
  crates belongs in that component's repository.

## License

Apache-2.0. Derivative work of [Apache Kafka](https://kafka.apache.org); see
[NOTICE](NOTICE).
