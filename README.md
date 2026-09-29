# tooling

Shared build and release inputs for the krabka-io repositories.

Krabka was one monorepo. It is now about a dozen repositories. Three kinds of
file could not follow a single component out, because every component needs
them: the release tooling, the container base-image recipes, and the Helm chart
signing key. They live here.

This repository holds no Rust. There is no `Cargo.toml`, no Bazel workspace and
no toolchain file. Nothing here is built. It also holds one AXL module, the
shared `rustdoc-site` task of the Aspect CLI.

## Directories

| Directory | What is in it | Who uses it |
| --------- | ------------- | ----------- |
| [`release/`](release/README.md) | Publish gate, version bumper, crates.io bootstrap, and the release-plz templates | Every krabka-io Rust repository |
| [`packaging/`](packaging/README.md) | The Creusot verifier toolchain recipe and a local-binary Dockerfile | krabka-broker, local runs |
| [`aspect/`](aspect/) | The AXL module that exports the `rustdoc-site` task, and the Krabka theme of the pages it publishes | Every krabka-io Rust repository that publishes API documentation |
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

## How a repository consumes the AXL module

The root `MODULE.aspect` of this repository is an AXL module. A consumer adds
it to its own `MODULE.aspect` as an archive dependency:

```python
axl_archive_dep(
    name = "krabka_tooling",
    urls = ["https://github.com/krabka-io/tooling/archive/0123456789abcdef0123456789abcdef01234567.tar.gz"],
    integrity = "sha512-...",
    strip_prefix = "tooling-0123456789abcdef0123456789abcdef01234567",
    auto_use_tasks = True,
    dev = True,
)
```

`auto_use_tasks = True` registers the tasks that the module declares. The
Aspect CLI accepts only `.tar.gz` archives. It does not resolve dependencies of
a module, so the module holds everything it needs.

The module exports only `rustdoc-site`. The `axl-tests` task in `.aspect/`
serves this repository and is not exported. Every consumer defines its own
`axl-tests` task, and a second task with that name would break it.

To move a consumer to a newer revision:

1. Pick a tag or a commit of this repository. Build the archive URL from it:
   `https://github.com/krabka-io/tooling/archive/<ref>.tar.gz`.
2. Compute the digest of the archive and prefix it with `sha512-`:

   ```
   curl -sL <url> | openssl dgst -sha512 -binary | openssl base64 -A
   ```

3. Write the new URL, `integrity` and `strip_prefix` in `MODULE.aspect`. The
   prefix is `tooling-<ref>`. For a tag, drop a leading `v` from the ref.

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
