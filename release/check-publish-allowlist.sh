#!/usr/bin/env bash
# Check that a krabka-io Rust workspace publishes exactly the crates its
# allowlist names, and that release-plz.toml agrees with cargo metadata.
#
# Run it from the root of the repository under test:
#
#   /path/to/tooling/release/check-publish-allowlist.sh [allowlist-file]
#
# The allowlist file holds one crate name per line. `#` starts a comment and
# blank lines are ignored. It defaults to `publish-allowlist.txt` in the
# working directory, which is the repository that owns the crates.
set -euo pipefail

allowlist_file="${1:-publish-allowlist.txt}"
if [ ! -f "${allowlist_file}" ]; then
    echo "no allowlist file at ${allowlist_file}" >&2
    echo "write one crate name per line, then run this script again" >&2
    exit 1
fi

metadata_file="$(mktemp)"
trap 'rm -f "${metadata_file}"' EXIT

cargo metadata --no-deps --format-version 1 >"${metadata_file}"

python3 - "${metadata_file}" "${allowlist_file}" <<'PY'
import json
import pathlib
import sys
import tomllib

allowlist_path = pathlib.Path(sys.argv[2])
allowlist = {
    line.split("#", 1)[0].strip()
    for line in allowlist_path.read_text().splitlines()
    if line.split("#", 1)[0].strip()
}

metadata_path = pathlib.Path(sys.argv[1])
metadata = json.loads(metadata_path.read_text())
packages = {package["name"]: package for package in metadata["packages"]}

def is_publishable(package):
    publish = package.get("publish")
    return publish is None or publish != []

publishable = {
    name for name, package in packages.items() if is_publishable(package)
}
unexpected_publishable = sorted(publishable - allowlist)
private_allowlisted = sorted(allowlist - publishable)
private_runtime_dependencies = sorted(
    f"{name} -> {dependency['name']}"
    for name in allowlist & packages.keys()
    for dependency in packages[name]["dependencies"]
    if dependency["name"] in packages
    and dependency["name"] not in allowlist
    and dependency["kind"] != "dev"
)
versioned_workspace_dev_dependencies = sorted(
    f"{name} -> {dependency['name']}"
    for name in allowlist & packages.keys()
    for dependency in packages[name]["dependencies"]
    if dependency["name"] in packages
    and dependency["kind"] == "dev"
    and dependency["req"] != "*"
)

release_plz = tomllib.loads(pathlib.Path("release-plz.toml").read_text())
release_package_entries = release_plz.get("package", [])
release_names = [package["name"] for package in release_package_entries]
release_entries = {
    package["name"]: package for package in release_package_entries
}
duplicate_release_entries = sorted(
    name for name in set(release_names) if release_names.count(name) > 1
)
unknown_release_entries = sorted(release_entries.keys() - packages.keys())

missing_public_entries = sorted(allowlist - release_entries.keys())
misconfigured_public_entries = sorted(
    name
    for name in allowlist & release_entries.keys()
    if release_entries[name].get("publish") is not True
    or release_entries[name].get("release") is not True
)

private_packages = set(packages) - allowlist
missing_private_entries = sorted(private_packages - release_entries.keys())
misconfigured_private_entries = sorted(
    name
    for name in private_packages & release_entries.keys()
    if release_entries[name].get("publish") is not False
    or release_entries[name].get("release") is not False
)

errors = []
if unexpected_publishable:
    errors.append(
        "unexpected publishable workspace packages:\n"
        + "\n".join(unexpected_publishable)
    )
if private_allowlisted:
    errors.append(
        "allowlisted packages are not publishable in Cargo metadata:\n"
        + "\n".join(private_allowlisted)
    )
if private_runtime_dependencies:
    errors.append(
        "published packages depend on private workspace packages:\n"
        + "\n".join(private_runtime_dependencies)
    )
if versioned_workspace_dev_dependencies:
    errors.append(
        "published packages have versioned workspace dev-dependencies:\n"
        + "\n".join(versioned_workspace_dev_dependencies)
    )
if duplicate_release_entries:
    errors.append(
        "duplicate release-plz package entries:\n"
        + "\n".join(duplicate_release_entries)
    )
if unknown_release_entries:
    errors.append(
        "release-plz package entries without workspace packages:\n"
        + "\n".join(unknown_release_entries)
    )
if missing_public_entries:
    errors.append(
        "allowlisted packages missing release-plz public entries:\n"
        + "\n".join(missing_public_entries)
    )
if misconfigured_public_entries:
    errors.append(
        "allowlisted packages without release-plz publish=true/release=true:\n"
        + "\n".join(misconfigured_public_entries)
    )
if missing_private_entries:
    errors.append(
        "private packages missing release-plz private entries:\n"
        + "\n".join(missing_private_entries)
    )
if misconfigured_private_entries:
    errors.append(
        "private packages without release-plz publish=false/release=false:\n"
        + "\n".join(misconfigured_private_entries)
    )

if errors:
    print("\n\n".join(errors), file=sys.stderr)
    print(
        "add publish = false, update release-plz.toml, or update the allowlist intentionally",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY
