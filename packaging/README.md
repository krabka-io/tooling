# Base-image build inputs

Krabka builds its container images **without a Dockerfile**, from APK packages.
[melange](https://github.com/chainguard-dev/melange) compiles the packages and
[apko](https://github.com/chainguard-dev/apko) assembles the OCI image. This
directory holds the shared inputs. A component repository keeps only the parts
that describe its own image.

| File | What it builds | Who consumes it |
| ---- | -------------- | --------------- |
| [`melange/krabka.yaml`](melange/krabka.yaml) | The `krabka` APK and one subpackage per server binary | Every repository that ships a server image |
| [`melange/krabka-demo.yaml`](melange/krabka-demo.yaml) | The all-in-one observability demo payload | `krabka-io/krabka-o11y-demo` |
| [`melange/creusot-toolchain.yaml`](melange/creusot-toolchain.yaml) | The Creusot deductive verifier toolchain APK | `krabka-io/krabka-broker` |
| [`apko/creusot-toolchain.yaml`](apko/creusot-toolchain.yaml) | The verifier image around that APK | `krabka-io/krabka-broker` |
| [`docker/Dockerfile.local-binary`](docker/Dockerfile.local-binary) | A throwaway image around a binary you already built | Local runs and end-to-end tests |

## The melange recipes are a reference

`melange/krabka.yaml` names every server binary in one `cargo build`, the way
the old monorepo built them: one pass over the shared dependency graph, then a
subpackage per image. No single repository holds all of those crates any more.
A component repository copies the recipe and cuts the package list, the `--bin`
list and the subpackage list down to its own binaries. The copy keeps the
toolchain pin, the `/var/cache/melange` cache handling and the `dist/` staging
step, because those parts are what make the build reproducible and cached.

`krabka-io/krabka-broker` already owns `packaging/base.apko.yaml` and its
lockfile. That file is the runtime base layer. It is not duplicated here.

## Creusot verifier toolchain

The `creusot-toolchain` recipe builds the dev and CI verifier image for formal
proofs. The image is single-arch, runs as root, and carries no attestation by
design, because the project never ships it to users. See the verification
document in `krabka-io/krabka-broker` for verifier usage and pin management.

## Architectures

Each user-facing image is a multi-arch OCI index:

| Platform      | apko arch | Runs natively on                              |
| ------------- | --------- | --------------------------------------------- |
| `linux/amd64` | `x86_64`  | Intel and AMD hosts                           |
| `linux/arm64` | `aarch64` | Apple Silicon (M1-M4), AWS Graviton and others |

The release workflow compiles the packages natively on a runner of each
architecture, without QEMU, and then assembles one index with apko. The tag
points at the index, so `docker pull`, `docker run` and Kubernetes select the
matching variant.

## Attestations

Each published image carries two keyless
[Sigstore](https://www.sigstore.dev/) attestations:

- **SLSA build provenance** records how, where and from which commit the build
  made the image. See [SLSA v1](https://slsa.dev/).
- **SPDX SBOM** is the bill of materials apko generated for the image.

The build stores both in GitHub's attestation store and pushes them to GHCR as
OCI referrers. Verify one with the GitHub CLI, against the repository that
released the image:

```sh
gh attestation verify oci://ghcr.io/krabka-io/krabka-broker:latest \
  --repo krabka-io/krabka-broker

gh attestation verify oci://ghcr.io/krabka-io/krabka-broker:latest \
  --repo krabka-io/krabka-broker \
  --predicate-type https://spdx.dev/Document
```

`cosign` reads the same referrers:

```sh
cosign verify-attestation \
  --type slsaprovenance1 \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/krabka-io/krabka-broker/' \
  ghcr.io/krabka-io/krabka-broker:latest
```
