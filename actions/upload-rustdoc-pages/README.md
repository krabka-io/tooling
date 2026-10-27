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
