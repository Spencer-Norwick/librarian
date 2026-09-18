# Contributing

Thanks for helping make a small reading tool easier to trust and use. Bug reports, confusing first-run steps, and focused fixes are welcome.

## Report a problem

[Open an issue](https://github.com/Spencer-Norwick/librarian/issues) with:

- Your OS and Python version.
- The command you ran, what you expected, and what happened.
- A small reproduction using the [sample essay](tests/fixtures/demo/ExampleAda_ReadingWithCare_2026_essay.txt) or other invented text.

Remove private filenames, excerpts, paths, credentials, and delivery recipients from logs. Use [security reporting](SECURITY.md) for sensitive issues.

## Work on the code

Use Python 3.11 or newer. From a clone:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,pdf]'
python -m pytest -q
python scripts/check-installed-package.py
```

The package check builds and installs a wheel in a temporary environment, then exercises the CLI without the source checkout. CI runs on Linux and macOS with Python 3.11 and 3.14.

Keep changes focused. Read [AGENTS.md](AGENTS.md) for the safety and metadata rules, and open a pull request describing the problem, resulting behavior, and validation. Include regression coverage for data-loss risks, privacy boundaries, delivery retries, and index-format changes. Follow the [walkthrough](docs/examples.md) when changing the first-run experience.

The design stays simple: plain files, one Markdown index, no database or wiki. Prefer deterministic local operations. Add dependencies or model calls only when they materially improve the result.

Use temporary synthetic workspaces. Never commit real readings, private settings, provider hooks, credentials, or generated personal drafts. Do not exercise real email or Messages delivery in tests. Demo screenshots must use invented content and show actual command output; label any hand-written reading notes.
