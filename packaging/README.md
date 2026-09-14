# Base-image build inputs

Krabka builds its container images **without a Dockerfile**. Each component
repository builds its own image with Bazel:
[apko](https://github.com/chainguard-dev/apko) (through `rules_apko`) assembles
a locked Wolfi base, and [`rules_img`](https://github.com/bazel-contrib/rules_img)
adds the Bazel-built binaries as layers, makes the multi-platform index and
pushes it. `krabka-io/krabka-broker/packaging/BUILD.bazel` is the reference
setup. This directory holds only the inputs that no single component repository
owns.

| File | What it builds | Who consumes it |
| ---- | -------------- | --------------- |
| [`melange/creusot-toolchain.yaml`](melange/creusot-toolchain.yaml) | The Creusot deductive verifier toolchain APK | `krabka-io/krabka-broker` |
| [`apko/creusot-toolchain.yaml`](apko/creusot-toolchain.yaml) | The verifier image around that APK | `krabka-io/krabka-broker` |
| [`docker/Dockerfile.local-binary`](docker/Dockerfile.local-binary) | A throwaway image around a binary you already built | Local runs and end-to-end tests |

## Component images

No shared package recipe builds the component images. The old
`melange/krabka.yaml` built every server binary in one monorepo `cargo build`,
and no repository holds that crate set now, so it was removed. Each component
repository owns its `packaging/` directory: an apko base config with its lock
file, and the `rules_img` targets for its own binaries.

`krabka-io/krabka-broker` owns `packaging/base.apko.yaml` and its lockfile. That
file is the runtime base layer. It is not duplicated here.

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

A `v*` tag builds both platforms. Bazel builds the binaries for each platform,
and `rules_img` assembles one index. The tag points at the index, so
`docker pull`, `docker run` and Kubernetes select the matching variant. Pushes
to `main` build `linux/amd64` only.

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
