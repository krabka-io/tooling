"""Check external trait links with stable rustdoc and the patched metadata."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class DependencyRootTests(unittest.TestCase):
    def test_external_trait_links_use_versioned_roots(self):
        dependency = '''//! # Per style
pub struct Context;
/// A dependency trait.
pub trait Paint {
    /// Set the foreground.
    fn fg(&self) {}
    /// Calls [fg](Self::fg()). See [crate docs](crate#per-style).
    /// Accepts a [Context].
    fn paint(&self) {}
}
impl<T> Paint for T {}
'''
        for patch in sorted(Path(__file__).parent.glob('*.patch')):
            with self.subTest(patch=patch.name):
                match = re.search(r'^\+(#!\[doc\(html_root_url = "([^"]+)"\)\])$', patch.read_text(), re.M)
                self.assertIsNotNone(match, 'Patch must add an HTML root attribute')
                attribute, url = match.groups()
                with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as directory:
                    root = Path(directory)
                    (root / 'dep.rs').write_text(attribute + '\n' + dependency)
                    (root / 'consumer.rs').write_text('extern crate dep;\npub struct Example;\n')
                    subprocess.run(['rustc', '--crate-name', 'dep', '--crate-type', 'lib', str(root / 'dep.rs'), '-o', str(root / 'libdep.rlib')], check=True, capture_output=True)
                    subprocess.run(['rustdoc', '--crate-name', 'consumer', str(root / 'consumer.rs'), '--extern', f'dep={root}/libdep.rlib', '-o', str(root / 'site')], check=True, capture_output=True)
                    html = (root / 'site/consumer/struct.Example.html').read_text()
                    self.assertIn(f'href="{url}dep/trait.Paint.html#method.fg"', html)
                    self.assertIn(f'href="{url}dep/index.html#per-style"', html)
                    self.assertIn(f'href="{url}dep/struct.Context.html"', html)
                    self.assertNotIn('href="Self::fg()"', html)
                    self.assertNotIn('href="crate#per-style"', html)
                    self.assertNotIn('href="Context"', html)


if __name__ == '__main__':
    unittest.main()
