# tooling

Shared build and release inputs for the krabka-io repositories.

Krabka was one monorepo. It is now about a dozen repositories. Three kinds of
file could not follow a single component out, because every component needs
them: the release tooling, the container base-image recipes, and the Helm chart
signing key. They live here.

This repository holds no Rust. There is no `Cargo.toml`, no Bazel workspace and
no toolchain file. Nothing here is built.

## Directories

| Directory | What is in it | Who uses it |
| --------- | ------------- | ----------- |
| [`release/`](release/README.md) | Publish gate, version bumper, crates.io bootstrap, and the release-plz templates | Every krabka-io Rust repository |
| [`packaging/`](packaging/README.md) | melange package recipes and apko image configs | The repositories that ship a container image |
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
| [`scripts/test-doc-examples.sh`](scripts/test-doc-examples.sh) | Builds and runs the documented streams examples, then guards against snippet drift | `krabka-streams-rs` |

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

## What is not here

- `packaging/base.apko.yaml` and its lockfile. `krabka-io/krabka-broker` owns
  the runtime base layer.
- Anything a single component owns. A build script that names one component's
  crates belongs in that component's repository.

## License

Apache-2.0. Derivative work of [Apache Kafka](https://kafka.apache.org); see
[NOTICE](NOTICE).
