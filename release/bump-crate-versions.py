#!/usr/bin/env python3
"""Bump krabka workspace crate versions in checked-in Cargo files.

The script updates:
  * the root workspace package version,
  * any explicit package versions for workspace crates,
  * krabka path-dependency version requirements in Cargo.toml files, and
  * krabka package versions recorded in Cargo.lock.

It intentionally only rewrites versions associated with packages whose names
start with `krabka-` (plus the root workspace package version), so unrelated
third-party dependency versions are left untouched.

The workspace is the git repository the script runs in, not the repository
that holds the script, because this tool is shared by every krabka-io Rust
repository. Pass `--root` to name a different workspace.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

CRATE_NAME_RE = re.compile(r'^name\s*=\s*"(krabka-[^"]+)"$')
VERSION_RE = re.compile(r'^(?P<prefix>version\s*=\s*)"(?P<version>[^"]+)"(?P<suffix>.*)$')
WORKSPACE_VERSION_RE = re.compile(
    r'(?ms)(^\[workspace\.package\]\n(?:.*?\n)*?^version\s*=\s*)"[^"]+"'
)
KRABKA_DEP_VERSION_RE = re.compile(
    r'(?m)^(?P<prefix>krabka-[A-Za-z0-9_-]+\s*=\s*\{[^\n}]*?\bversion\s*=\s*)"[^"]+"'
)


def workspace_root() -> Path:
    """Return the root of the git repository the script runs in."""
    top = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        capture_output=True,
        check=True,
        text=True,
    )
    return Path(top.stdout.strip())


def replace_workspace_package_version(text: str, version: str) -> str:
    text, count = WORKSPACE_VERSION_RE.subn(rf'\g<1>"{version}"', text, count=1)
    if count != 1:
        raise RuntimeError("could not find [workspace.package] version in root Cargo.toml")
    return text


def replace_krabka_dependency_versions(text: str, version: str) -> str:
    return KRABKA_DEP_VERSION_RE.sub(rf'\g<prefix>"{version}"', text)


def replace_explicit_crate_package_version(text: str, version: str) -> str:
    """Replace an explicit package version when this manifest is a krabka crate."""
    lines = text.splitlines(keepends=True)
    in_package = False
    is_krabka_package = False
    package_version_index: int | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('['):
            if in_package:
                break
            in_package = stripped == '[package]'
            continue
        if not in_package:
            continue
        if CRATE_NAME_RE.match(stripped):
            is_krabka_package = True
        if VERSION_RE.match(stripped):
            package_version_index = index

    if is_krabka_package and package_version_index is not None:
        line = lines[package_version_index]
        newline = '\n' if line.endswith('\n') else ''
        bare = line[:-1] if newline else line
        lines[package_version_index] = VERSION_RE.sub(
            rf'\g<prefix>"{version}"\g<suffix>', bare
        ) + newline
    return ''.join(lines)


def update_cargo_toml(path: Path, version: str, root: Path) -> bool:
    original = path.read_text()
    text = original
    if path == root / 'Cargo.toml':
        text = replace_workspace_package_version(text, version)
    text = replace_explicit_crate_package_version(text, version)
    text = replace_krabka_dependency_versions(text, version)
    if text != original:
        path.write_text(text)
        return True
    return False


def update_cargo_lock(path: Path, version: str) -> bool:
    original = path.read_text()
    lines = original.splitlines(keepends=True)
    in_package = False
    current_is_krabka = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == '[[package]]':
            in_package = True
            current_is_krabka = False
            continue
        if in_package and stripped.startswith('name = '):
            current_is_krabka = CRATE_NAME_RE.match(stripped) is not None
            continue
        if in_package and current_is_krabka and stripped.startswith('version = '):
            newline = '\n' if line.endswith('\n') else ''
            lines[index] = f'version = "{version}"{newline}'
            current_is_krabka = False

    text = ''.join(lines)
    if text != original:
        path.write_text(text)
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', help='target crate version, for example 0.3.1')
    parser.add_argument(
        '--root',
        type=Path,
        default=None,
        help='workspace root; defaults to the git repository the script runs in',
    )
    args = parser.parse_args()

    root = args.root.resolve() if args.root else workspace_root()

    changed: list[Path] = []
    for path in [root / 'Cargo.toml', *sorted((root / 'crates').glob('*/Cargo.toml'))]:
        if update_cargo_toml(path, args.version, root):
            changed.append(path)

    lock_path = root / 'Cargo.lock'
    if lock_path.exists() and update_cargo_lock(lock_path, args.version):
        changed.append(lock_path)

    for path in changed:
        print(path.relative_to(root))
    print(f'updated {len(changed)} file(s) to {args.version}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
