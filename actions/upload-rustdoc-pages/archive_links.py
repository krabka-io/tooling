#!/usr/bin/env python3
"""Check static and selected rendered links against final Pages archives."""

import argparse
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.ids = set()
        self.base = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id') is not None:
            self.ids.add(attrs['id'])
        if tag == 'a' and attrs.get('name'):
            self.ids.add(attrs['name'])
        if tag == 'base' and self.base is None and attrs.get('href'):
            self.base = attrs['href']
        attribute = {'a': 'href', 'area': 'href', 'link': 'href',
                     'script': 'src', 'img': 'src', 'iframe': 'src'}.get(tag)
        if attribute and attrs.get(attribute):
            self.links.append(attrs[attribute])

    handle_startendtag = handle_starttag


def public_root(value):
    url = urlsplit(value)
    if (url.scheme not in ('http', 'https') or not url.netloc or url.query
            or url.fragment or url.username or url.password
            or unquote(url.path) != url.path or '\\' in value
            or any(p in ('.', '..') for p in url.path.split('/'))):
        raise ValueError(f'Expected an absolute HTTP site URL without query or fragment: {value}')
    return urlunsplit((url.scheme, url.netloc.lower(), url.path.rstrip('/') + '/', '', ''))


@dataclass
class Mount:
    root: str
    archive: Path
    files: dict = field(default_factory=dict)
    pages: dict = field(default_factory=dict)

    def __post_init__(self):
        self.root = public_root(self.root)
        with tarfile.open(self.archive) as package:
            seen = set()
            for entry in package:
                path = PurePosixPath(entry.name)
                if path.is_absolute() or '..' in path.parts or '\\' in entry.name:
                    raise ValueError(f'Unsafe archive path: {entry.name}')
                name = path.as_posix()
                if name in seen:
                    raise ValueError(f'Duplicate archive entry: {entry.name}')
                seen.add(name)
                if entry.isdir():
                    continue
                if not entry.isfile():
                    raise ValueError(f'Non-regular archive entry: {entry.name}')
                with package.extractfile(entry) as content:
                    self.files[name] = content.read()
                if name.endswith(('.html', '.htm')):
                    page = Page()
                    page.feed(self.files[name].decode('utf-8'))
                    self.pages[name] = page
        if not self.pages:
            raise ValueError(f'No HTML pages in archive: {self.archive}')

    def locate(self, url):
        parts = urlsplit(url)
        root = urlsplit(self.root)
        if (parts.scheme, parts.netloc.lower()) != (root.scheme, root.netloc):
            return None
        path = unquote(parts.path)
        if path == root.path.rstrip('/'):
            path += '/'
        if not path.startswith(root.path):
            return None
        relative = path[len(root.path):]
        if '\\' in relative or '..' in PurePosixPath(relative).parts:
            raise ValueError(f'Unsafe URL path: {url}')
        if relative in self.files:
            return relative
        index = relative.rstrip('/') + '/index.html' if relative else 'index.html'
        return index if index in self.files else None


class Gate:
    def __init__(self, mounts):
        roots = [mount.root for mount in mounts]
        if len(set(roots)) != len(roots):
            raise ValueError('Duplicate component site URL')
        self.mounts = sorted(mounts, key=lambda mount: len(mount.root), reverse=True)
        self.errors = []
        self.checked = 0
        self.external = set()
        self.non_http = 0
        self.rendered = 0
        self.rendered_ids = {}

    def lookup(self, url):
        parts = urlsplit(url)
        for mount in self.mounts:
            root = urlsplit(mount.root)
            if ((parts.scheme, parts.netloc.lower()) == (root.scheme, root.netloc)
                    and (unquote(parts.path).startswith(root.path)
                         or unquote(parts.path) == root.path.rstrip('/'))):
                return mount, mount.locate(url)
        return None, None

    def check(self, origin, href, base=None, rendered=False):
        try:
            scheme = urlsplit(href).scheme.lower()
            if scheme in ('mailto', 'tel', 'data') or href in ('javascript:void(0)', 'javascript:;'):
                self.non_http += 1
                return
            if scheme and scheme not in ('http', 'https'):
                raise ValueError(f'Malformed or unsupported href scheme: {href}')
            target = urljoin(base or origin, href)
            mount, name = self.lookup(target)
            if mount is None:
                origin_parts = urlsplit(target)
                if any(urlsplit(m.root).netloc == origin_parts.netloc.lower() for m in self.mounts):
                    raise ValueError(f'Unmapped same-site destination: {target}; supply its component archive')
                self.external.add(target)
                return
            self.checked += 1
            if name is None:
                raise ValueError(f'Missing destination: {target}')
            raw_fragment = urlsplit(target).fragment
            fragment = unquote(raw_fragment)
            if fragment and name in mount.pages:
                ids = self.rendered_ids.get((mount.root, name), mount.pages[name].ids)
                # Rustdoc source-line ranges select existing line anchors in JS.
                line_range = re.fullmatch(r'(\d+)-(\d+)', fragment)
                source_range = (line_range and '/src/' in '/' + name
                                and name.endswith('.rs.html')
                                and int(line_range[1]) <= int(line_range[2])
                                and all(part in ids for part in line_range.groups()))
                if (raw_fragment not in ids and fragment not in ids and not source_range
                        and fragment.lower() != 'top'):
                    raise ValueError(f'Missing fragment: {target}')
        except ValueError as error:
            self.errors.append(f'{origin}: {href!r}: {error}')

    def static(self):
        for mount in self.mounts:
            for name, page in sorted(mount.pages.items()):
                origin = urljoin(mount.root, name)
                base = urljoin(origin, page.base) if page.base else origin
                for href in page.links:
                    self.check(origin, href, base)

    def render(self, paths, primary):
        self.render_many([(paths, primary)])

    def render_many(self, selections):
        for paths, primary in selections:
            if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
                raise ValueError('Rendered pages must be a nonempty JSON list of HTML paths')
        # Optional dependency. Fail if requested checks cannot run.
        from playwright.sync_api import sync_playwright
        with sync_playwright() as engine:
            browser = engine.chromium.launch(headless=True)
            options = {'service_workers': 'block'}
            if os.environ.get('ARCHIVE_LINKS_USER_AGENT'):
                options['user_agent'] = os.environ['ARCHIVE_LINKS_USER_AGENT']
            context = browser.new_context(**options)

            def serve(route):
                mount, name = self.lookup(route.request.url)
                if mount is None:
                    netloc = urlsplit(route.request.url).netloc.lower()
                    if any(urlsplit(m.root).netloc == netloc for m in self.mounts):
                        self.errors.append(f'Unmapped same-site resource: {route.request.url}; '
                                           'supply its component archive')
                    route.abort()
                elif name is None:
                    self.errors.append(f'Rendered resource missing: {route.request.url}')
                    route.fulfill(status=404, body='Not found')
                else:
                    if name.endswith('/index.html') or name == 'index.html':
                        path = urlsplit(route.request.url).path
                        if not path.endswith(('/', '.html')):
                            route.fulfill(status=301, headers={'Location': path + '/'})
                            return
                    route.fulfill(body=mount.files[name], content_type=
                                  mimetypes.guess_type(name)[0] or 'application/octet-stream')

            context.route('**/*', serve)
            context.route_web_socket('**/*', lambda socket: socket.close())
            documents = []
            for paths, primary in selections:
                for path in paths:
                    url = urljoin(primary.root, path)
                    mount, name = self.lookup(url)
                    if mount is not primary or name not in primary.pages:
                        raise ValueError(f'Render page is not HTML in the primary archive: {path}')
                    page = context.new_page()
                    page.on('pageerror', lambda error: self.errors.append(f'Render error: {error}'))
                    page.goto(url, wait_until='networkidle')
                    # Collect all IDs first, so links between rendered pages can resolve.
                    self.rendered_ids[(primary.root, name)] = set(page.locator('[id], a[name]').evaluate_all(
                        '(nodes) => nodes.map(node => node.id || node.getAttribute("name"))'))
                    documents.append((page.url, page.locator('[href], [src]').evaluate_all(
                        '(nodes) => nodes.filter(n => n.tagName !== "BASE").map(n => '
                        'n.getAttribute("href") || n.getAttribute("src"))'),
                        page.evaluate('document.baseURI')))
                    self.rendered += 1
                    page.close()
            for origin, links, base in documents:
                for href in links:
                    self.check(origin, href, base, rendered=True)
            context.close()
            browser.close()

    def report(self):
        return {'archives': len(self.mounts),
                'html_pages': sum(len(m.pages) for m in self.mounts),
                'checked_links': self.checked, 'rendered_pages': self.rendered,
                'external_unchecked': sorted(self.external),
                'non_http_skipped': self.non_http, 'errors': self.errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--site-url', default='https://pages.invalid/')
    parser.add_argument('--components', type=Path,
                        help='JSON list of {site_url, archive}; paths relative to this file')
    parser.add_argument('--render-pages', type=Path, help='JSON list of archive-relative HTML paths')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        primary = Mount(args.site_url, args.archive)
        mounts = [primary]
        if args.components:
            for component in json.loads(args.components.read_text()):
                mounts.append(Mount(component['site_url'],
                                    args.components.parent / component['archive']))
        gate = Gate(mounts)
        if args.render_pages:
            gate.render(json.loads(args.render_pages.read_text()), primary)
        gate.static()
        report = gate.report()
        if args.report:
            args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        return bool(gate.errors)
    except (ValueError, OSError, tarfile.TarError, ImportError, KeyError, TypeError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
