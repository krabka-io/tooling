# Krabka Helm charts

The charts moved out of the monorepo with the components they install. Each
chart now lives beside its own source. This directory holds the one thing all
of them share: the chart signing public key.

## Where each chart lives

| Chart | Repository |
| ----- | ---------- |
| `krabka-operator` | [`krabka-io/krabka-operator`](https://github.com/krabka-io/krabka-operator) under `charts/` |
| `krabka-rebalancer` | [`krabka-io/krabka-rebalancer`](https://github.com/krabka-io/krabka-rebalancer) under `charts/` |
| `krabka-schema-registry` | [`krabka-io/krabka-schema-registry`](https://github.com/krabka-io/krabka-schema-registry) under `charts/` |

Each repository packages and signs its own chart on release. Each one then
pushes the tarball, the `.prov` file and the cosign bundle to the shared index.

## The published index

The aggregated Helm repository index lives in
[`krabka-io/krabka-io.github.io`](https://github.com/krabka-io/krabka-io.github.io)
and is served from **https://krabka-io.github.io/charts**. It is the only
index a user adds. It lists the charts from all three component repositories:

```sh
helm repo add krabka https://krabka-io.github.io/charts
helm repo update
helm search repo krabka
```

The chart `version` and `appVersion` fields and the default image tags track
the crate release. The package step in each component repository derives them
from that workspace's `Cargo.toml`, so there is no version to edit by hand.

## Verifying charts

Every published chart tarball is signed and carries supply-chain provenance.
The chart signing **public key is in this directory** as
[`krabka-charts.pub.asc`](krabka-charts.pub.asc). It holds one key, so a key
rotation does not break verification of an older chart. A mirror of the file is
at `https://krabka-io.github.io/charts/krabka-charts.pub.asc`.

### PGP provenance (`helm install --verify`)

```sh
curl -fsSL https://krabka-io.github.io/charts/krabka-charts.pub.asc \
  | gpg --dearmor > krabka-keyring.gpg
helm install my-op krabka/krabka-operator --verify --keyring ./krabka-keyring.gpg
```

### Keyless cosign signature

Each tarball has a detached Sigstore bundle `<chart>.tgz.cosign.bundle` next to
it in the index. The certificate identity names the repository that released
the chart:

```sh
cosign verify-blob \
  --bundle krabka-operator-<version>.tgz.cosign.bundle \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/krabka-io/krabka-operator/' \
  krabka-operator-<version>.tgz
```

### SLSA build provenance attestation

```sh
gh attestation verify krabka-operator-<version>.tgz --repo krabka-io/krabka-operator
```

## Maintainers: signing keys

The release workflow of each component repository does the signing:

- **cosign** and the **SLSA attestation** are keyless, through Sigstore OIDC.
  They need no secret, and they run on every non-pull-request build.
- **PGP `.prov`** activates when the repository has the `HELM_GPG_KEY`,
  `HELM_GPG_KEY_ID` and `HELM_GPG_PASSPHRASE` secrets. `HELM_GPG_KEY` is the
  base64 ASCII-armored private key. Set the three secrets in each repository
  that publishes a chart, from the same key.

The matching public key is [`krabka-charts.pub.asc`](krabka-charts.pub.asc).
Rotate the private key and this file together: append the new public key here,
then update the secrets. Keep the private key and its revocation certificate in
a secrets manager.

The key is `Krabka Charts <charts@krabka.dev>`, RSA 4096, fingerprint
`74A6 7D5C F9AE 199A 45D2  2E42 594B D543 4544 D339`. It expires on
2028-09-11.

### The old Crabka key is revoked

Charts signed before 2026-09-12 used a different key, with the user ID
`Crabka Charts <charts@crabka.dev>`. That key is no longer valid and this
repository no longer carries it. **Signatures made with it do not verify.**

Krabka is undeployed, so no released artifact depends on the old signatures. Do
not re-add the old public key to make an old `.prov` file verify. Sign the chart
again with the current key instead.

The new key has no passphrase, so `HELM_GPG_PASSPHRASE` is an empty string.
Set a passphrase on the private key if you prefer, and update that secret to
match.
