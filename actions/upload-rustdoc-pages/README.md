# Upload rustdoc Pages

This action packages an assembled rustdoc site for GitHub Pages. It does not
build crates, configure Pages, or deploy the artifact. It requires Linux,
Python 3, and GNU tar. GitHub-hosted Ubuntu runners provide these tools.

## Consumer change

Keep the existing build, `aspect rustdoc-site`, and `actions/configure-pages`
steps. Replace `actions/upload-pages-artifact` with this action. Pin the action
to the reviewed tooling commit. Do not copy its Python files into consumers.

```yaml
- name: Upload API documentation
  uses: krabka-io/tooling/actions/upload-rustdoc-pages@<full-reviewed-commit-sha>
  with:
    path: site
```

Keep the deployment in a separate job with `needs: build`. The build job must
fail if this action fails. Do not set `continue-on-error`. The action uploads
the default `github-pages` artifact. Call it once per build job.

The action has its own revision pin. The `MODULE.aspect` pin controls site
assembly and does not select this action. This change needs no AXL module
update because it does not change the assembly task.

## File selection

The Pages upload action excludes dot-directories by default. Rustdoc can put
generated source HTML under a `.cache` directory. This makes valid Source
links fail after publication.

This action creates a fresh staging directory under `RUNNER_TEMP`. It copies
ordinary documentation files. It also copies hidden source pages only when
a local rustdoc Source anchor links to them. The allowed path has this form:

```text
[site prefix/]src/<crate>/home/runner/.cache/bazel/_bazel_runner/.../*.rs.html
```

Only `.cache` may be a dot-prefixed path segment. Other hidden files stay
excluded. Unlinked hidden source pages stay excluded. The action rejects
symlinks, missing local Source targets, and links that escape the site.
The input must contain at least one local rustdoc Source link.

The upload action enables hidden files only for this staging directory.
The final step checks the upload action's actual tar archive. It checks
file membership and bytes. It rejects missing, extra, duplicate, unsafe,
or non-regular entries. A failed check blocks the dependent deploy job.

This checks packaging. It does not scan ordinary documentation for secrets
or repair unrelated documentation links. Build only public documentation.

## Checks and rollout

Run the behavioral tests from the tooling checkout:

```sh
python3 -m unittest discover -s actions/upload-rustdoc-pages -p 'test_*.py' -v
```

The tests use GNU tar. They reproduce the original hidden-file omission.
They also check injected hidden files, symlinks, missing targets, and escapes.
The real-rustdoc test requires `rustdoc`. CI installs it and runs this action
on a generated-source fixture through the pinned Pages upload action.

First migrate krabka-protocol. Validate its full assembled output in PR CI.
Then migrate krabka-broker, krabka-client-rs, krabka-operator, krabka-gateway,
krabka-connect, krabka-rebalancer, krabka-streams-rs, and krabka-cli.
Each consumer needs the action pin and full-output validation. No consumer
deploys until its change is approved and merged.

## Final archive link gate

The action checks links in `RUNNER_TEMP/artifact.tar` after the upload step.
It reads archive bytes directly. It does not extract or modify the archive.
The existing membership and byte checks still run first. A failed link check
fails the build job and blocks a dependent deployment job.

Set `site-url` to the public URL of the archive root. Include its deployment
prefix. The default is `https://pages.invalid/`. This default checks relative
links without a public host. Set the real URL to check absolute same-site links.

```yaml
- name: Upload and check API documentation
  id: pages
  uses: krabka-io/tooling/actions/upload-rustdoc-pages@<full-reviewed-commit-sha>
  with:
    path: site
    site-url: https://example.org/api/component/
    component-archives: docs/component-archives.json
    render-pages: docs/render-pages.json
```

Omit the last two inputs if the site does not need them. The `link-report`
output gives the path to a JSON report. Save it as a CI artifact when needed.
The report lists unchecked external links. External HTTP links are not fetched.
A passing gate does not prove that external links work.

The static check reads every archived HTML page. It checks anchor destinations,
stylesheet links, scripts, images and iframe sources. It resolves relative
links, root-relative links, base URLs, directory indexes, queries and encoded
fragments. It checks HTML IDs and legacy named anchors. Rustdoc source ranges
such as `#1-4` require both endpoint IDs. Non-HTML resource fragments are not
checked. The gate rejects unknown URL schemes, including malformed Rust paths
such as `Self::attr()`. It preserves `mailto:`, `tel:` and `data:` links. It skips the rustdoc
control links `javascript:void(0)` and `javascript:;`.
Bare references such as `crate#per-style` must resolve to a file and fragment.
The gate does not rewrite links or infer redirects.

### Cross-component links

A missing destination on a configured host fails the gate. Do not add a broad
exclusion for another component. Supply its exact upload archive instead.
The optional `component-archives` file is a JSON list:

```json
[
  {
    "site_url": "https://example.org/api/other/",
    "archive": "../artifacts/other.tar"
  }
]
```

Archive paths are relative to this JSON file. The gate checks links inside
these archives too. Nested URL mounts use the most specific prefix. Each
mount must have a unique site URL. A component on another host is treated as
external unless its archive is configured. If CI checks that component in a
separate job, keep that check as a required dependency of deployment. The
report does not count external links as checked.

### Rendered navigation

Use `render-pages` for pages whose navigation depends on JavaScript. Supply a
JSON list of archive-relative HTML paths, such as `["crate/index.html"]`.
Install Python Playwright and its Chromium browser before calling the action:

```sh
python3 -m pip install playwright==1.64.1
python3 -m playwright install --with-deps chromium
```

The browser serves only bytes from the configured archives. It blocks external
requests. It checks links in the resulting DOM after network idle. It fails on
missing local resources and script exceptions. It does not click controls or
exercise search. Add separate interaction checks for those paths. Missing
Playwright or Chromium fails a requested rendered check. No rendered checks run
when the input is absent. Static checks do not prove script-generated links.

Run the gate on an existing upload archive without staging or uploading:

```sh
python3 actions/upload-rustdoc-pages/archive_links.py artifact.tar \
  --site-url https://example.org/api/component/ \
  --components docs/component-archives.json \
  --render-pages docs/render-pages.json \
  --report links.json
```

CI tests known-bad and corrected archives. The tests cover missing Source HTML,
malformed Rust references, missing fragments, component mounts, and links
inserted by an archived script. The real-rustdoc fixture also passes through
the pinned Pages upload action and the final archive gate.

### Baseline retention

`retention-days` defaults to 90 and is forwarded to the Pages uploader. Repository
or organization policy can impose a shorter limit. Retention is finite: refresh
and review the composition lock before any referenced artifact expires. Existing
artifacts are not extended by changing this input. Expired or deleted baseline
artifacts remain hard failures; validation never silently selects a replacement.
