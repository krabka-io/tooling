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

Component repositories do not package or sign their charts. The index job in
krabka-io.github.io does both. See below.

## The published index

The aggregated Helm repository index lives in
[`krabka-io/krabka-io.github.io`](https://github.com/krabka-io/krabka-io.github.io)
and is served from https://krabka.io/charts. It is the only index a user adds,
and it lists the charts from all three component repositories:

```sh
helm repo add krabka https://krabka.io/charts
helm repo update
helm search repo krabka
```

The older host, `https://krabka-io.github.io/charts`, redirects to it.

The `helm-index` workflow runs `scripts/build-helm-index.sh` daily at 03:00 UTC,
on a push to `main`, and on demand. On each run it deletes the index, packages
every chart again from its repository, and signs each one. A chart's `version`
and `appVersion` come from `[workspace.package] version` in that repository's
`Cargo.toml`. A repository with no workspace version uses the `Chart.yaml`
version.

## Verifying charts

Each chart carries a Helm PGP provenance file, `<chart>.tgz.prov`. That is the
only signature. No chart has a cosign signature or an SLSA attestation.

The public key is [`krabka-charts.pub.asc`](krabka-charts.pub.asc) in this
directory. Check its fingerprint before you trust it:

```text
Krabka Charts <charts@krabka.dev>
74A6 7D5C F9AE 199A 45D2  2E42 594B D543 4544 D339
```

```sh
curl -fsSLO https://raw.githubusercontent.com/krabka-io/tooling/main/charts/krabka-charts.pub.asc
gpg --import krabka-charts.pub.asc
gpg --fingerprint charts@krabka.dev
gpg --dearmor < krabka-charts.pub.asc > krabka-keyring.gpg
helm install my-op krabka/krabka-operator --verify --keyring ./krabka-keyring.gpg
```

## Maintainers: signing keys

The `helm-index` workflow in krabka-io.github.io signs every chart. It reads
three organization Actions secrets in `krabka-io`. They are visible only to
that repository:

| Secret | Value |
| ------ | ----- |
| `HELM_GPG_KEY` | The ASCII-armored private key, base64-encoded |
| `HELM_GPG_KEY_ID` | Part of the key's user ID, for example `charts@krabka.dev` |
| `HELM_GPG_PASSPHRASE` | Unset for this key |

`HELM_GPG_KEY_ID` must match the key's user ID. Helm finds the key by its
identity, and a fingerprint does not match.

The current key has no passphrase, so leave `HELM_GPG_PASSPHRASE` unset. Do not
set it to an empty string. The script passes a passphrase file only when the
secret has a value, and Helm fails with `Error: EOF` on an empty passphrase
file. If you give the key a passphrase, set this secret to it.

When `HELM_GPG_KEY` is unset, the job publishes charts with no `.prov` file.

To rotate the key, replace `krabka-charts.pub.asc` here and update the two
secrets. The next index run signs every chart again with the new key. Keep the
private key and its revocation certificate in a secrets manager.

The key is RSA 4096 and expires on 2028-09-11.

### The old Crabka key is revoked

Charts signed before 2026-09-12 used a different key, with the user ID
`Crabka Charts <charts@crabka.dev>`. That key is no longer valid and this
repository no longer carries it. Signatures made with it do not verify.

Krabka is undeployed, so no released artifact depends on the old signatures. Do
not re-add the old public key to make an old `.prov` file verify. Sign the chart
again with the current key instead.
