# Dependency documentation roots

Stable rustdoc needs an HTML root for external dependency links. A dependency
can supply that root with `#![doc(html_root_url = "...")]`. Without the root,
rustdoc can emit the original Rust reference as an HTML href in inherited
blanket-trait documentation. Examples include `Self::fg()` and `crate#per-style`.

These patches add that metadata to the dependency source. The yansi patch also
qualifies macro-generated trait links as `crate::Paint::*`. This gives rustdoc
a concrete trait owner instead of an unresolved `Self`. The tracing-core root
is needed for tracing reexports such as `Subscriber`. The patches do not change
runtime code. Each patch applies to one crate version and names that version's
docs.rs root. Consumers must select the exact version in their rules_rs
`crate.annotation` and apply the patch with `patch_args = ["-p1"]`.

The metadata travels with compiled dependency information. Consumer rustdoc can
then resolve inherited trait references without unstable compiler flags or
rewriting generated anchors. This problem is not specific to Bazel. Cargo doc
can resolve more links when it also generates dependency documentation locally.

When a dependency version changes, review its upstream `html_root_url`. Remove
the patch if upstream supplies it. Otherwise make and test a new versioned patch.
Do not apply an old patch through a wildcard version annotation.

Run the stable compiler regression:

```sh
python3 -m unittest discover -s patches/rustdoc -p 'test_*.py' -v
```

Also regenerate a real consumer's rustdoc and run the archive link checker.
The compiler regression does not check the contents of the external docs.rs site.
