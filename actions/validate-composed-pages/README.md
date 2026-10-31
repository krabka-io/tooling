# Validate composed Pages

This composite action validates **all HTML links in every mounted archive**. It
uses the existing archive checker and collects rendered IDs across components
before checking rendered links. It does not deploy or request live websites.
Callers install `gh`, Python 3, and (when any rendered pages are selected)
Playwright with Chromium. Provide a `GH_TOKEN` with Actions read access to all
listed repositories; the default repository token may not have cross-repository
access. Capture the report with an `if: always()` artifact-upload step.

## Site-owned composition and lock

A composition declares routing; an explicit snapshot operation resolves it to a
reviewable lock. Never use snapshot resolution as a validation fallback.

```json
{
  "schema_version": 1,
  "components": [{
    "id": "website",
    "site_url": "https://docs.example/",
    "repo": "example/website",
    "artifact_name": "github-pages",
    "render_pages": ["index.html"]
  }]
}
```

`artifact_name` is optional and defaults to `github-pages`. Snapshot considers
nonexpired artifacts from completed successful default-branch `push` or
`workflow_dispatch` runs, chooses the newest eligible artifact ID, verifies its
metadata and downloaded ZIP digest, and checks its tar safety. This is artifact
selection, **not evidence that the run was deployed**. Review selected provenance
against deployment records before approving the baseline. Baselines requiring
exact deployed-state fidelity should be populated from those deployment records.
There is no automatic production build, artifact dispatch, or deployment.

```sh
python3 actions/validate-composed-pages/compose.py \
  --snapshot --manifest site-composition.json --lock-out site-archives.lock.json \
  --work-dir "$RUNNER_TEMP" --report snapshot-report.json
```

Missing inputs produce a per-component failure report and nonzero exit; no lock
is written unless all components resolve. An existing lock is not overwritten on
failure; always honor the snapshot exit status.

The strict validation lock has these exact component fields:

```json
{
  "schema_version": 1,
  "components": [{
    "id": "website",
    "site_url": "https://docs.example/",
    "repo": "example/website",
    "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "run_id": 123,
    "artifact_id": 456,
    "artifact_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "render_pages": ["index.html"]
  }]
}
```

The digest is over the GitHub Actions **ZIP wrapper**, not `artifact.tar`. The
wrapper must contain exactly one regular `artifact.tar` entry. Tar contents are
checked by the existing safe Mount reader. No arbitrary ZIP extraction occurs.
Duplicate mounts, IDs, files, and files shadowed by child mounts fail validation.
Mount prefixes are allowed for a root site plus component sites but cannot hide
parent files. External hosts remain reported as unchecked, not fetched.

## Candidate replacement

A candidate file replaces exactly one component's baseline archive. Other mounts
remain pinned. Its provenance is recorded separately, not attributed to the
replaced baseline run or digest:

```json
{
  "id": "website",
  "archive": "candidate-artifact.tar",
  "repo": "example/website",
  "head_sha": "cccccccccccccccccccccccccccccccccccccccc",
  "run_id": 789,
  "sha256": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
}
```

`archive` is relative to the candidate JSON file (or absolute). `run_id` and
`sha256` are optional. The actual candidate tar digest is always recorded;
`sha256`, when supplied, must match. Candidate repo must match the component.
Local provenance is caller-declared, not remotely attested.

```yaml
- uses: example/tooling/actions/validate-composed-pages@FULL_COMMIT_SHA
  env:
    GH_TOKEN: ${{ secrets.CROSS_REPO_ACTIONS_READ_TOKEN }}
  with:
    manifest: site-archives.lock.json
    candidate: candidate.json
    report: composed-pages-report.json
```

Or use `upload-rustdoc-pages` with paired `composition-lock` and `component-id`
inputs. It stages and uploads the candidate normally, then runs this full graph
check instead of its standalone gate. Do not combine composition mode with
standalone `component-archives` or `render-pages`; the lock owns these selections.
`candidate-head-sha` defaults to PR head SHA, falling back to workflow SHA.

Validation reports are emitted on success and failure, including malformed locks,
missing/expired artifacts, API failures, bad digests, and link errors. They retain
manifest digest, available component provenance, per-archive tar digests, static
link errors, and rendered-page counts. GitHub API error stderr is not copied into
reports to avoid leaking credential details. No baseline is fetched by floating
run name or latest-successful lookup during validation.
