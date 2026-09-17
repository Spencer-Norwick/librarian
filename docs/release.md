# Alpha release checklist

Release from the reviewed integration branch after these steps, in order:

Routine owner-authorized development is delivered through a pushed branch and a checked, merged pull request. Do not defer that cloud backup/integration until a versioned release. This checklist covers the separate alpha announcement, tag, and distribution publication.

1. Run the full test suite and verify CI against a clean checkout. Build an sdist and wheel; install the wheel into a fresh environment outside the checkout and check `librarian --help`, `mount --check`, and `init`.
2. Follow [examples.md](examples.md) in a new synthetic workspace. Confirm previews, ingest/enrich/maintain, short selection, and a Markdown-only weekly draft. Do not use real reading files or delivery endpoints for validation.
3. Inspect the complete release diff and tracked files. Scan the full Git history for secrets and private content, not just filenames. Confirm ignored reading files, hooks, backups, config, and recipient information remain private. Rotate any exposed credential rather than relying on deletion alone.
4. Ask an independent person to install from scratch and produce their first synthetic weekly draft using only the public instructions. Fix any blocking issue and record the tested OS/Python versions. Automated agent review does not replace this usability check.
5. Choose a fresh alpha version/tag, update package version and changelog, and record validation and known limits in release notes. Review the built artifacts for unintended files. Merge/push/tag and publish the GitHub release only when publication is authorized; package-index publication is a separate decision.

The current public repository is experimental. Do not label it stable until supported-platform installation and real-world failure recovery have been exercised. Keep release notes honest about optional model hooks, macOS delivery integrations, and remaining usability limits.
