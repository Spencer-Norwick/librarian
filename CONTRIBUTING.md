# Contributing

Keep the project a small, inspectable CLI with flat files and one Markdown index. Read [AGENTS.md](AGENTS.md) for the safety and metadata rules before changing behavior.

Use Python 3.11 or newer and an isolated environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,pdf]'
python -m pytest -q
python scripts/check-installed-package.py
```

Work on a focused branch and open a pull request describing the problem, resulting behavior, and validation. Include regression tests for data-loss risks, privacy boundaries, delivery retries, and index-format changes. Prefer deterministic local operations; add dependencies or model calls only when their value justifies the complexity.

Use synthetic temporary workspaces for development. Do not commit real reading files, local config, provider hooks, credentials, generated digests, or personal delivery recipients. Do not run email or Messages delivery during tests. Run the [synthetic walkthrough](docs/examples.md) when changing the user workflow, and verify a built wheel when changing packaging.

For bug reports, include the command, Python/OS version, expected behavior, and a minimal synthetic reproduction. Redact filenames, text excerpts, hook output, paths, and config that contain private information. See [SECURITY.md](SECURITY.md) for sensitive reports.
