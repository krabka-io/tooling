"""Archive-level regressions for destinations, fragments and generated links."""

import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from archive_links import Gate, Mount


class ArchiveLinksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def mount(self, files, root='https://docs.example/api/', name='artifact.tar'):
        archive = self.root / name
        with tarfile.open(archive, 'w') as package:
            for path, content in files.items():
                content = content.encode()
                entry = tarfile.TarInfo(path if path.startswith('/') else './' + path)
                entry.size = len(content)
                package.addfile(entry, io.BytesIO(content))
        return Mount(root, archive)

    def gate(self, files):
        gate = Gate([self.mount(files)])
        gate.static()
        return gate

    def test_relative_root_index_fragment_and_query(self):
        gate = self.gate({'index.html': '<a href="module/">module</a>',
                          'module/index.html': '<a href="/api/index.html?q=x#top">root</a>',
                          'another.html': '<a href="module#hello%20world">index</a>',
                          'asset.svg': '<svg/>',
                          'unused.html': '<img src="asset.svg?version=1">'})
        self.assertEqual(len(gate.errors), 2)  # Two missing fragments.
        gate = self.gate({'index.html': '<div id="top"></div><a href="module/">module</a>',
                          'module/index.html': '<a name="hello world"></a><a href="/api/?q=x#top">root</a>',
                          'another.html': '<a href="module#hello%20world">index</a>'})
        self.assertEqual(gate.errors, [])
        self.assertEqual(gate.checked, 3)
        gate = self.gate({'index.html': '<a href="/api#encoded%3CT%3E">root</a>'
                          '<div id="encoded%3CT%3E"></div>'})
        self.assertEqual(gate.errors, [])

    def test_proven_malformed_and_bare_reference_families(self):
        for href in ('Self::attr()', 'super::Subscriber', 'ObjectMeta::new',
                     'other_crate::Type', 'crate#per-style', 'Context', 'javascript:alert(1)'):
            with self.subTest(href=href):
                gate = self.gate({'index.html': f'<a href="{href}">bad</a>'})
                self.assertEqual(len(gate.errors), 1)

    def test_hidden_source_missing_from_final_archive(self):
        source = 'src/crate/home/runner/.cache/generated.rs.html'
        files = {'index.html': f'<a class="src" href="{source}#1-4">Source</a>'}
        self.assertIn('Missing destination', self.gate(files).errors[0])
        files[source] = '<a id="1"></a><a id="4"></a>'
        self.assertEqual(self.gate(files).errors, [])
        files[source] = '<a id="1"></a>'
        self.assertIn('Missing fragment', self.gate(files).errors[0])

    def test_external_and_legitimate_non_http_links_are_reported(self):
        gate = self.gate({'index.html': '<a href="https://other.example/a">external</a>'
                          '<a href="mailto:a@example.com">mail</a><a href="tel:123">phone</a>'
                          '<a href="javascript:void(0)">rustdoc control</a>'})
        self.assertEqual(gate.errors, [])
        self.assertEqual(gate.report()['external_unchecked'], ['https://other.example/a'])
        self.assertEqual(gate.non_http, 3)

    def test_base_and_encoded_destination(self):
        gate = self.gate({'index.html': '<base href="sub/"><a href="hello%20world.html#ok">ok</a>',
                          'sub/hello world.html': '<p id="ok">ok</p>'})
        self.assertEqual(gate.errors, [])

    def test_component_mounts_validate_cross_links_and_fragments(self):
        first = self.mount({'index.html': '<a href="/other/type.html#good">type</a>'})
        gate = Gate([first])
        gate.static()
        self.assertIn('Unmapped same-site', gate.errors[0])
        second = self.mount({'type.html': '<div id="good"></div>'},
                            'https://docs.example/other/', 'other.tar')
        gate = Gate([first, second])
        gate.static()
        self.assertEqual(gate.errors, [])
        second.pages['type.html'].ids.clear()
        gate.static()
        self.assertIn('Missing fragment', gate.errors[0])

    def test_archive_safety(self):
        for name in ('../escape.html', '/absolute.html', 'a/../../escape.html', 'a\\bad.html'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unsafe archive'):
                self.mount({name: 'bad'})
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            archive = self.root / 'unsafe.tar'
            with tarfile.open(archive, 'w') as package:
                entry = tarfile.TarInfo('link')
                entry.type = kind
                entry.linkname = 'elsewhere'
                package.addfile(entry)
            with self.assertRaisesRegex(ValueError, 'Non-regular'):
                Mount('https://docs.example/', archive)

    def test_duplicate_and_empty_archives_fail(self):
        with self.assertRaisesRegex(ValueError, 'No HTML'):
            self.mount({'main.js': '// no HTML'})
        mount = self.mount({'index.html': 'ok'})
        with tarfile.open(mount.archive, 'a') as package:
            entry = tarfile.TarInfo('index.html')
            package.addfile(entry, io.BytesIO(b''))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            Mount(mount.root, mount.archive)

    def test_cli_returns_failure_and_writes_report_for_bad_archive(self):
        mount = self.mount({'index.html': '<a href="missing.html">missing</a>'})
        report = self.root / 'report.json'
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('archive_links.py')),
                                 str(mount.archive), '--report', str(report)], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(json.loads(report.read_text())['errors']), 1)

    def test_empty_render_selection_is_rejected(self):
        mount = self.mount({'index.html': 'ok'})
        with self.assertRaisesRegex(ValueError, 'nonempty JSON list'):
            Gate([mount]).render([], mount)

    def test_rendered_links_from_archived_script(self):
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            self.skipTest('Playwright is not installed')
        mount = self.mount({'index.html': '<body><script src="main.js"></script>',
                            'main.js': 'document.body.innerHTML += `<a href="missing.html">dynamic</a>`;'})
        gate = Gate([mount])
        gate.static()
        self.assertEqual(gate.errors, [])
        gate.render(['index.html'], mount)
        self.assertTrue(any('Missing destination' in error for error in gate.errors))
        fixed = self.mount({'index.html': '<body><script src="main.js"></script>',
                            'main.js': 'document.body.innerHTML += `<a href="ok.html#yes">dynamic</a>`;',
                            'ok.html': '<div id="yes"></div>'})
        gate = Gate([fixed])
        gate.render(['index.html'], fixed)
        self.assertEqual(gate.errors, [])
        removed = self.mount({'index.html': '<body><div id="gone"></div>'
                              '<script src="main.js"></script>',
                              'main.js': 'document.getElementById("gone").remove();'
                              'document.body.innerHTML += `<a href="#gone">removed</a>`;'})
        gate = Gate([removed])
        gate.render(['index.html'], removed)
        self.assertTrue(any('Missing fragment' in error for error in gate.errors))


if __name__ == '__main__':
    unittest.main()
