import io
import json
import os
import textwrap
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from compose import (candidate_input, collisions, digest, execute, fetch, main,
                     snapshot, validate_manifest)
from archive_links import Gate, Mount


class CompositionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.component = dict(id='root', site_url='https://example.test/', repo='org/site',
                              head_sha='a' * 40, run_id=12, artifact_id=34,
                              artifact_digest='sha256:' + 'b' * 64, render_pages=[])

    def archive(self, name, html):
        path = self.root / name
        with tarfile.open(path, 'w') as package:
            data = html.encode()
            info = tarfile.TarInfo('index.html')
            info.size = len(data)
            package.addfile(info, io.BytesIO(data))
        return path

    def manifest(self, components):
        path = self.root / 'lock.json'
        path.write_text(json.dumps(dict(schema_version=1, components=components)))
        return path

    def test_complete_graph_cycles_and_broken_reference(self):
        a = self.component
        b = dict(a, id='other', site_url='https://example.test/other/', artifact_id=35)
        first = self.archive('a.tar', '<a href="/other/#ok">other</a><div id="ok"></div>')
        second = self.archive('b.tar', '<a href="/#ok">root</a><div id="ok"></div>')
        report = {'components': [], 'errors': []}
        with patch('compose.fetch', side_effect=[first, second]):
            execute(self.manifest([a, b]), None, self.root, report)
        self.assertFalse(report['errors'])
        self.assertEqual(report['links']['checked_links'], 2)
        second = self.archive('bad.tar', '<a href="/absent/">broken in reference</a><div id="ok"></div>')
        report = {'components': [], 'errors': []}
        work = self.root / 'next'
        work.mkdir()
        with patch('compose.fetch', side_effect=[first, second]):
            execute(self.manifest([a, b]), None, work, report)
        self.assertTrue(any('Missing destination' in error for error in report['errors']))

    def test_override_has_separate_provenance_and_skips_download(self):
        archive = self.archive('candidate.tar', '<p>valid</p>')
        candidate = self.root / 'candidate.json'
        candidate.write_text(json.dumps(dict(id='root', archive=archive.name,
                                            repo='org/site', head_sha='c' * 40, sha256=digest(archive))))
        report = {'components': [], 'errors': []}
        with patch('compose.fetch') as download:
            execute(self.manifest([self.component]), candidate, self.root, report)
        download.assert_not_called()
        self.assertEqual(report['components'][0]['source'], 'candidate')
        self.assertEqual(report['components'][0]['head_sha'], 'c' * 40)
        self.assertNotIn('artifact_id', report['components'][0])
        data = json.loads(candidate.read_text())
        data['sha256'] = 'sha256:' + '0' * 64
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            candidate_input(data, [self.component], self.root)
        data['id'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            candidate_input(data, [self.component], self.root)

    def test_duplicate_and_invalid_lock_fields(self):
        for changes in ({'artifact_digest': 'bad'}, {'run_id': True}, {'head_sha': 'bad'},
                        {'site_url': 'https://example.test'}, {'render_pages': ['../a.html']},
                        {'render_pages': ['a\\bad.html']}, {'render_pages': ['a/./bad.html']}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_manifest(dict(schema_version=1, components=[dict(self.component, **changes)]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            validate_manifest(dict(schema_version=1, components=[self.component, self.component]))

    def test_mount_collisions_and_shadowing(self):
        first = Mount('https://example.test/', self.archive('first.tar', 'one'))
        second = Mount('https://example.test/', self.archive('second.tar', 'two'))
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            collisions([first, second])
        child = Mount('https://example.test/index.html/', second.archive)
        # A child prefix can intercept the parent file URL even without the exact same filename.
        with self.assertRaisesRegex(ValueError, 'hidden'):
            collisions([first, child])

    def metadata(self):
        return dict(id=34, expired=False, digest=self.component['artifact_digest'],
                    workflow_run=dict(id=12, head_sha='a' * 40))

    def run_metadata(self):
        return dict(id=12, head_sha='a' * 40, repository=dict(full_name='org/site'),
                    status='completed', conclusion='success', head_repository=dict(full_name='org/site'))

    def test_bad_artifact_provenance_fails_before_download(self):
        for changes in ({'expired': True}, {'digest': 'sha256:' + 'e' * 64},
                        {'workflow_run': dict(id=99, head_sha='a' * 40)},
                        {'workflow_run': dict(id=12, head_sha='e' * 40)}):
            with self.subTest(changes=changes):
                with patch('compose.gh_json', side_effect=[dict(self.metadata(), **changes), self.run_metadata()]), \
                        patch('compose.subprocess.run') as download, self.assertRaises(ValueError):
                    fetch(self.component, self.root)
                download.assert_not_called()

    def test_fork_or_wrong_repository_provenance_rejected(self):
        for field in ('repository', 'head_repository'):
            run = dict(self.run_metadata(), **{field: dict(full_name='fork/site')})
            with patch('compose.gh_json', side_effect=[self.metadata(), run]), \
                    patch('compose.subprocess.run') as download, self.assertRaisesRegex(ValueError, 'provenance'):
                fetch(self.component, self.root)
            download.assert_not_called()

    def test_upload_action_paired_inputs_and_candidate_metadata(self):
        action = Path(__file__).parents[1] / 'upload-rustdoc-pages' / 'action.yml'
        script = textwrap.dedent(action.read_text().rsplit('      run: |\n', 1)[1])
        staged = self.root / 'stage'
        staged.mkdir()
        report = self.root / 'paired-report.json'
        # Assert every action-specific shell variable comes from this step's declared env.
        final_step = action.read_text().split('    - name: Check links in the final Pages archive', 1)[1]
        self.assertIn('        STAGED_PATH: ${{ steps.stage.outputs.path }}', final_step)
        env = dict(os.environ, COMPOSITION_LOCK='missing-lock.json', COMPONENT_ID='',
                   COMPONENT_ARCHIVES='', RENDER_PAGES='', LINK_REPORT=str(report),
                   STAGED_PATH=str(staged), RUNNER_TEMP=str(self.root),
                   GITHUB_REPOSITORY='org/site', CANDIDATE_SHA='c' * 40, GITHUB_RUN_ID='789',
                   ACTION_PATH=str(action.parent))
        result = subprocess.run(['bash', '-c', script], env=env, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('together', json.loads(report.read_text())['errors'][0])
        env['COMPONENT_ID'] = 'root'
        result = subprocess.run(['bash', '-c', script], env=env, capture_output=True)
        self.assertEqual(result.returncode, 1)  # Missing lock must fail closed.
        self.assertEqual(json.loads((self.root / 'candidate.json').read_text()),
                         dict(id='root', archive=str(self.root / 'artifact.tar'), repo='org/site',
                              head_sha='c' * 40, run_id=789))
        self.assertEqual(json.loads(report.read_text())['status'], 'failed')

    def test_download_digest_and_safe_zip_wrapper(self):
        archive = self.archive('source.tar', 'okay')
        for member in ('artifact.tar', '../escape', 'sub/artifact.tar'):
            wrapper = self.root / 'source.zip'
            with zipfile.ZipFile(wrapper, 'w') as package:
                package.writestr(member, archive.read_bytes())
            component = dict(self.component, artifact_digest=digest(wrapper))
            metadata = dict(self.metadata(), digest=component['artifact_digest'])
            def download(*args, **kwargs):
                kwargs['stdout'].write(wrapper.read_bytes())
            with patch('compose.gh_json', side_effect=[metadata, self.run_metadata()]), \
                    patch('compose.subprocess.run', side_effect=download):
                if member == 'artifact.tar':
                    self.assertEqual(fetch(component, self.root).read_bytes(), archive.read_bytes())
                else:
                    with self.assertRaisesRegex(ValueError, 'ZIP'):
                        fetch(component, self.root)
        with patch('compose.gh_json', side_effect=[self.metadata(), self.run_metadata()]), \
                patch('compose.subprocess.run', side_effect=download), self.assertRaisesRegex(ValueError, 'digest mismatch'):
            fetch(self.component, self.root)

    def test_failure_report_even_invalid_manifest(self):
        path = self.root / 'invalid.json'
        path.write_text('{}')
        report = self.root / 'report.json'
        self.assertTrue(main(['--manifest', str(path), '--report', str(report), '--work-dir', str(self.root)]))
        self.assertEqual(json.loads(report.read_text())['status'], 'failed')

    def test_snapshot_selects_successful_default_branch_non_pr_artifact(self):
        component = {k: self.component[k] for k in ('id', 'site_url', 'repo', 'render_pages')}
        composition = self.root / 'composition.json'
        composition.write_text(json.dumps(dict(schema_version=1, components=[component])))
        archive = self.archive('snapshot.tar', 'valid')
        artifacts = [dict(id=35, name='github-pages', expired=False,
                          workflow_run=dict(id=13, head_branch='main')),
                     dict(id=34, name='github-pages', expired=False,
                          workflow_run=dict(id=12, head_branch='main'))]
        def api(endpoint):
            if endpoint == 'repos/org/site':
                return {'default_branch': 'main'}
            run_id = int(endpoint.rsplit('/', 1)[1])
            return dict(self.run_metadata(), id=run_id, event='pull_request' if run_id == 13 else 'push',
                        head_branch='main')
        # Actual artifact digest is obtained from artifact-list metadata, not from run metadata.
        artifacts[1]['digest'] = self.component['artifact_digest']
        report = {'components': [], 'errors': []}
        lock = self.root / 'lock.json'
        with patch('compose.gh_json', side_effect=api), \
                patch('compose.fetch', return_value=archive) as download, \
                patch('compose.subprocess.run', return_value=subprocess.CompletedProcess(
                    [], 0, json.dumps([{'artifacts': artifacts}]).encode())):
            snapshot(composition, lock, self.root, report)
        self.assertEqual(report['errors'], [])
        self.assertEqual(json.loads(lock.read_text())['components'][0]['artifact_id'], 34)
        self.assertEqual(download.call_args.args[0]['run_id'], 12)
        self.assertEqual(report['lock_sha256'], digest(lock))

    def test_snapshot_missing_baseline_reports_each_component_and_no_lock(self):
        composition = self.root / 'composition.json'
        components = [{k: self.component[k] for k in ('id', 'site_url', 'repo', 'render_pages')}]
        components.append(dict(components[0], id='other', repo='org/other'))
        composition.write_text(json.dumps(dict(schema_version=1, components=components)))
        report = {'components': [], 'errors': []}
        lock = self.root / 'new-lock.json'
        with patch('compose.gh_json', return_value={'default_branch': 'main'}), \
                patch('compose.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'[{"artifacts":[]}]')):
            snapshot(composition, lock, self.root, report)
        self.assertEqual(len(report['errors']), 2)
        self.assertFalse(lock.exists())

    def test_render_across_components_collects_dynamic_ids_before_links(self):
        first = Mount('https://example.test/', self.archive('a.tar',
            '<a href="/other/#dynamic">other</a>'))
        second = Mount('https://example.test/other/', self.archive('b.tar',
            '<body><script>document.body.id="dynamic";</script>'))
        gate = Gate([first, second])
        gate.render_many([(['index.html'], first), (['index.html'], second)])
        gate.static()
        self.assertEqual(gate.errors, [])
        self.assertEqual(gate.rendered, 2)


if __name__ == '__main__':
    unittest.main()
