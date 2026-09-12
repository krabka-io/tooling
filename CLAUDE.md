# tooling: project-specific guidance

Shared build and release inputs for the krabka-io repositories. Read
[README.md](README.md) first for what each directory holds.

## This repository holds no Rust

There is no `Cargo.toml`, no Bazel workspace and no toolchain file. Do not add
one. A file that needs to compile belongs in the repository that owns the
crates it compiles.

Everything here is shell, Python, YAML or TOML.

## Compatibility

**Krabka is greenfield and undeployed.** There are no production users, no
persisted state to migrate, and no clients pinned to a specific build. Do not
write backwards-compatibility shims:

- No feature flag that gates new behavior behind a default-off switch
- No migration code or one-shot upgrader for a format change
- No deprecated-but-kept interface

When a schema, wire format or interface changes, change it.

The signing key in `charts/` is an exception, and it is not a shim. It holds
three public keys, so a chart signed with an older key still verifies. Keys
rotate. The format does not.

## What belongs here, and what does not

A file belongs here when more than one repository needs it. A file that names
one component's crates belongs in that component's repository. When in doubt,
list the repositories that would break if the file were deleted. One
repository means it goes there.

Every script acts on the git repository of the **working directory**. It never
resolves paths relative to its own location, because it is run from a checkout
of a different repository. Keep it that way when you add a script.

Do not hardcode a crate list in a script. `check-publish-allowlist.sh` reads
`publish-allowlist.txt` from the repository under test. Follow that pattern.

## Prose style

Write all prose in ASD-STE100 Simplified Technical English:

- One idea per sentence. Keep sentences short.
- Active voice. Name the actor.
- One word for one meaning. Do not vary a term for style.
- No marketing words. No "seamless", "robust", "comprehensive" or "leverage".
- No em dash strung through a sentence. No "not X, but Y". No one-line closer.

## Release Process

The krabka-io Rust repositories use **release-plz** for semantic versioning.
Conventional commits drive the bumps:

- `feat:` gives a minor version bump
- `fix:` gives a patch version bump
- `feat!:` gives a major version bump

This repository is not released. It has no version and publishes nothing. Use
conventional commits here anyway, because the same convention is in the
changelog template it ships.
