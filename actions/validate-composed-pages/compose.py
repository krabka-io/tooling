#!/usr/bin/env python3
"""Validate a reproducible set of GitHub Pages archives, without live-site requests."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'upload-rustdoc-pages'))
from archive_links import Gate, Mount, public_root


HEX = r'[0-9a-f]{64}'
SHA = r'[0-9a-f]{40}'
REPO = r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    return type(value) is int and value > 0


def validate_manifest(data):
    require(isinstance(data, dict) and set(data) == {'schema_version', 'components'},
            'Manifest requires schema_version and components only')
    require(type(data['schema_version']) is int and data['schema_version'] == 1,
            'Unsupported schema_version')
    components = data['components']
    require(isinstance(components, list) and components, 'components must be a nonempty list')
    ids, roots = set(), set()
    fields = {'id', 'site_url', 'repo', 'head_sha', 'run_id', 'artifact_id',
              'artifact_digest', 'render_pages'}
    for item in components:
        require(isinstance(item, dict) and set(item) == fields, 'Invalid component fields')
        require(isinstance(item['id'], str) and re.fullmatch(r'[a-z0-9][a-z0-9_-]*', item['id']),
                'Invalid component id')
        require(item['id'] not in ids, 'Duplicate component id')
        ids.add(item['id'])
        root = public_root(item['site_url'])
        require(root == item['site_url'], 'site_url must be canonical with trailing slash')
        require(root not in roots, 'Duplicate component site_url')
        roots.add(root)
        require(isinstance(item['repo'], str) and re.fullmatch(REPO, item['repo']), 'Invalid repo')
        require(isinstance(item['head_sha'], str) and re.fullmatch(SHA, item['head_sha']), 'Invalid head_sha')
        require(integer(item['run_id']) and integer(item['artifact_id']), 'Invalid run/artifact ID')
        require(isinstance(item['artifact_digest'], str)
                and re.fullmatch('sha256:' + HEX, item['artifact_digest']), 'Invalid artifact_digest')
        paths = item['render_pages']
        require(isinstance(paths, list) and len(paths) == len(set(map(str, paths))), 'Invalid render_pages')
        for path in paths:
            require(isinstance(path, str) and path and not path.startswith('/')
                    and '\\' not in path and '?' not in path and '#' not in path
                    and not any(p in ('.', '..', '') for p in path.split('/'))
                    and path.endswith(('.html', '.htm')), 'Invalid render page path')
    return components


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return 'sha256:' + result.hexdigest()


def gh_json(endpoint):
    result = subprocess.run(['gh', 'api', endpoint], check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    return json.loads(result.stdout)


def fetch(component, directory):
    repo = component['repo']
    metadata = gh_json(f'repos/{repo}/actions/artifacts/{component["artifact_id"]}')
    run = gh_json(f'repos/{repo}/actions/runs/{component["run_id"]}')
    require(metadata.get('id') == component['artifact_id'] and metadata.get('expired') is False,
            'Artifact identity mismatch or expired')
    require(metadata.get('workflow_run', {}).get('id') == component['run_id'], 'Artifact run mismatch')
    require(metadata.get('workflow_run', {}).get('head_sha') == component['head_sha'], 'Artifact commit mismatch')
    require(metadata.get('digest') == component['artifact_digest'], 'Artifact metadata digest mismatch')
    require(run.get('id') == component['run_id'] and run.get('head_sha') == component['head_sha']
            and run.get('repository', {}).get('full_name', '').lower() == repo.lower()
            and run.get('head_repository', {}).get('full_name', '').lower() == repo.lower(),
            'Run provenance mismatch')
    require(run.get('status') == 'completed' and run.get('conclusion') == 'success', 'Baseline run is not successful')
    wrapper = directory / 'download.zip'
    with wrapper.open('wb') as output:
        subprocess.run(['gh', 'api', f'repos/{repo}/actions/artifacts/{component["artifact_id"]}/zip'],
                       check=True, stdout=output, stderr=subprocess.PIPE)
    require(digest(wrapper) == component['artifact_digest'], 'Downloaded artifact digest mismatch')
    archive = directory / 'artifact.tar'
    # Never extract arbitrary ZIP paths, symlinks, or duplicate entries. Pages upload wraps one tar.
    with zipfile.ZipFile(wrapper) as package:
        entries = package.infolist()
        require(len(entries) == 1 and entries[0].filename == 'artifact.tar'
                and not entries[0].is_dir()
                and (entries[0].external_attr >> 16) & 0o170000 in (0, 0o100000),
                'Expected a ZIP containing only regular artifact.tar')
        with package.open(entries[0]) as source, archive.open('wb') as target:
            import shutil
            shutil.copyfileobj(source, target)
    return archive


def candidate_input(data, manifest, base):
    required = {'id', 'archive', 'repo', 'head_sha'}
    require(isinstance(data, dict) and required <= set(data)
            and not set(data) - required - {'run_id', 'sha256'}, 'Invalid candidate fields')
    matches = [c for c in manifest if c['id'] == data['id']]
    require(len(matches) == 1, 'Candidate id must replace exactly one component')
    require(data['repo'] == matches[0]['repo'], 'Candidate repo does not match component')
    require(isinstance(data['head_sha'], str) and re.fullmatch(SHA, data['head_sha']), 'Invalid candidate head_sha')
    require('run_id' not in data or integer(data['run_id']), 'Invalid candidate run_id')
    require(isinstance(data['archive'], str) and data['archive'], 'Invalid candidate archive')
    archive = (base / data['archive']).resolve()
    actual = digest(archive)
    if 'sha256' in data:
        require(isinstance(data['sha256'], str) and re.fullmatch('sha256:' + HEX, data['sha256']),
                'Invalid candidate sha256')
        require(actual == data['sha256'], 'Candidate archive digest mismatch')
    return archive, {**data, 'archive': str(archive), 'sha256': actual, 'source': 'candidate'}


def collisions(mounts):
    # Parent mounts may own routing pages beneath child prefixes, but must not shadow files.
    urls = {}
    for mount in mounts:
        for name in mount.files:
            url = mount.root + name
            require(url not in urls, f'Overlapping archive file: {url}')
            urls[url] = mount.root
    gate = Gate(mounts)
    for url, root in urls.items():
        owner, name = gate.lookup(url)
        require(owner.root == root and name is not None, f'File hidden by child mount: {url}')


def execute(manifest_path, candidate_path, work, report):
    components = validate_manifest(json.loads(manifest_path.read_text()))
    report['manifest_sha256'] = digest(manifest_path)
    candidate = None
    if candidate_path:
        data = json.loads(candidate_path.read_text())
        archive, provenance = candidate_input(data, components, candidate_path.parent)
        candidate = (data['id'], archive, provenance)
    mounts = []
    selections = []
    for component in components:
        entry = {'id': component['id'], 'site_url': component['site_url']}
        report['components'].append(entry)
        if candidate and candidate[0] == component['id']:
            archive, provenance = candidate[1:]
        else:
            provenance = {**component, 'source': 'baseline'}
            entry.update(provenance)
            directory = work / component['id']
            directory.mkdir()
            archive = fetch(component, directory)
        entry.update(provenance)
        entry['archive_sha256'] = digest(archive)
        mount = Mount(component['site_url'], archive)
        mounts.append(mount)
        selections.append((component['render_pages'], mount))
    collisions(mounts)
    gate = Gate(mounts)
    try:
        rendered = [(pages, mount) for pages, mount in selections if pages]
        if rendered:
            gate.render_many(rendered)
        gate.static()
    finally:
        report['links'] = gate.report()
    report['errors'].extend(gate.errors)


def snapshot(composition_path, lock_path, work, report):
    data = json.loads(composition_path.read_text())
    require(isinstance(data, dict) and set(data) == {'schema_version', 'components'}
            and data['schema_version'] == 1 and isinstance(data['components'], list)
            and data['components'], 'Invalid composition document')
    locked = []
    for component in data['components']:
        entry = {'id': component.get('id'), 'source': 'snapshot'}
        report['components'].append(entry)
        try:
            require(isinstance(component, dict) and {'id', 'site_url', 'repo', 'render_pages'} <= set(component)
                    and not set(component) - {'id', 'site_url', 'repo', 'render_pages', 'artifact_name'},
                    'Invalid composition component fields')
            repo = component['repo']
            require(isinstance(repo, str) and re.fullmatch(REPO, repo), 'Invalid repo')
            repository = gh_json(f'repos/{repo}')
            branch = repository['default_branch']
            # Explicit snapshot is the only operation permitted to resolve floating state.
            result = subprocess.run(['gh', 'api', '--paginate', '--slurp',
                                     f'repos/{repo}/actions/artifacts?per_page=100'], check=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            pages = json.loads(result.stdout)
            artifacts = [a for page in pages for a in page['artifacts']
                         if a.get('name') == component.get('artifact_name', 'github-pages')
                         and a.get('expired') is False
                         and a.get('workflow_run', {}).get('head_branch') == branch]
            selected = None
            for artifact in sorted(artifacts, key=lambda a: a['id'], reverse=True):
                run = gh_json(f'repos/{repo}/actions/runs/{artifact["workflow_run"]["id"]}')
                if (run.get('status') == 'completed' and run.get('conclusion') == 'success'
                        and run.get('event') in ('push', 'workflow_dispatch')
                        and run.get('head_branch') == branch):
                    selected = {k: component[k] for k in ('id', 'site_url', 'repo', 'render_pages')}
                    selected.update(head_sha=run['head_sha'], run_id=run['id'],
                                    artifact_id=artifact['id'], artifact_digest=artifact.get('digest'))
                    validate_manifest({'schema_version': 1, 'components': [selected]})
                    directory = work / str(artifact['id'])
                    directory.mkdir()
                    archive = fetch(selected, directory)
                    Mount(selected['site_url'], archive)
                    break
            require(selected is not None, f'No available successful default-branch Pages artifact for {repo}')
            locked.append(selected)
            entry.update(selected)
        except Exception as error:
            message = ('GitHub API operation failed' if isinstance(error, subprocess.CalledProcessError)
                       else f'{type(error).__name__}: {error}')
            entry['error'] = message
            report['errors'].append(f'{entry["id"]}: {message}')
    if not report['errors']:
        lock = {'schema_version': 1, 'components': locked}
        validate_manifest(lock)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + '\n')
        report['lock_sha256'] = digest(lock_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--lock-out', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    report = {'schema_version': 1, 'components': [], 'errors': [], 'status': 'failed'}
    try:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='composition-', dir=args.work_dir) as temporary:
            if args.snapshot:
                require(args.lock_out is not None and args.candidate is None,
                        'Snapshot requires --lock-out and does not accept --candidate')
                snapshot(args.manifest, args.lock_out, Path(temporary), report)
            else:
                require(args.lock_out is None, '--lock-out requires --snapshot')
                execute(args.manifest, args.candidate, Path(temporary), report)
        if not report['errors']:
            report['status'] = 'passed'
    except Exception as error:
        # subprocess stderr may contain auth details; retain a safe command-independent summary.
        report['errors'].append('GitHub API operation failed' if isinstance(error, subprocess.CalledProcessError)
                                else f'{type(error).__name__}: {error}')
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(f'Composed Pages validation: {report["status"]}; report: {args.report}')
    return report['status'] != 'passed'


if __name__ == '__main__':
    raise SystemExit(main())
