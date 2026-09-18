# Setup and optional models

[← Back to the README](../README.md)

The [quickstart](../README.md#get-started) gives you a local library with no account or model. This guide covers separate workspaces, settings, and optional enrichment.

## Choose your workspace

The current directory is the workspace. Activating a virtual environment makes the command available; it does not select a library.

To keep readings separate from the source checkout, install and activate the CLI first, then create a permanent folder:

```bash
mkdir "$HOME/my-reading-library"
cd "$HOME/my-reading-library"
librarian mount --check
librarian init
librarian mount --privacy local --model none
librarian mount --privacy local --model none --apply
```

`init` creates missing setup files immediately and preserves existing ones. `mount` previews settings; only `mount --apply` saves `_state/config.toml`. Setup checks may create missing workspace directories, but do not ingest readings or send them anywhere.

| Folder | Contents |
| --- | --- |
| `inbox/` | New reading files |
| `library/` | Reading files and `index.md` |
| `_state/` | Local settings, logs, optional model hooks |
| `_output/` | Weekly drafts and OCR copies |
| `_quarantine/` | Files set aside for manual review |

Keep configured paths inside the workspace. They cannot be absolute or contain `..`. The checkout ignores reading files and state; a separately initialized workspace must also be kept out of public repositories. Git ignores are not encryption or backups.

## Choose settings

Preview with `librarian mount` and explicit options, then repeat with `--apply`. Omitted privacy and model options preserve existing settings.

| Setting | Choices |
| --- | --- |
| `--privacy local` | Clear the model hook and disable automatic model assistance |
| `--privacy assisted` | Use a configured model only when explicitly requested |
| `--privacy automatic` | Configure automatic assistance; the approval setting below still applies |
| `--model none` | Disable model enrichment |
| `--model auto` | Detect available tools without choosing a provider command |
| `--model codex` | Check for Codex; still needs a JSON-compatible hook |
| `--model custom` | Use the command supplied with `--model-command` |
| `--digest none\|notify\|apply\|email` | Choose the recommended digest command; does not install a schedule |

For most setups, choose `local` without a model or `assisted` with a model you trust. A fresh workspace has catalog lookup off. Changing an existing workspace to `local` preserves its catalog setting: set `use_catalog_lookup = false` in `_state/config.toml` if you previously enabled it. Automatic enrichment and scheduled writes should be deliberate choices. Explicit command flags can request external services even when defaults are local; email always requires an explicit delivery command.

## Optional model assistance

A model can suggest summaries, tags, and reading questions. **Provider adapters are not bundled.** You need a small wrapper for your chosen provider or local model. Organizing files and adding notes by hand work without one.

Keep the wrapper and credentials in ignored local state, for example `_state/model-enrich-local`. It must read JSON from stdin and print only enrichment JSON to stdout. Send only the needed metadata and text to the provider.

Test it with synthetic input before using a real reading:

```bash
printf '%s' '{"work":{"title":"Synthetic Test","author":"Example, Ada","year":"2026","work_type":"essay"},"text_excerpt":"This invented essay recommends choosing one reading and recording a thought afterward."}' \
  | _state/model-enrich-local
```

Expected output shape:

```json
{
  "summary": "A concise, specific summary.",
  "primer_prompts": ["A question about the argument.", "A question to consider while reading."],
  "tags": ["reading"],
  "related": "None."
}
```

After creating and testing the hook, preview and save its configuration:

```bash
librarian mount --privacy assisted --model custom --model-command "_state/model-enrich-local"
librarian mount --privacy assisted --model custom --model-command "_state/model-enrich-local" --apply
librarian enrich "Title"
```

The path above is a hook **you create**, not an included file. Review the provider, excerpt limits, and proposed notes before using real files or saving with `--apply`.

### What leaves your machine

The hook receives metadata and a text excerpt. It may send both to an external provider **even in a dry run**. `--apply` controls local saves, not model calls.

Relevant settings in `_state/config.toml`:

```toml
[behavior]
use_model_assistance = false
model_command = ["_state/model-enrich-local"]
model_max_input_chars = 12000
require_external_model_approval = true
```

With approval `true` (or absent), an explicit `librarian enrich` or `--enrich` approves that batch; automatic enrichment is skipped. For unattended enrichment, deliberately set both `use_model_assistance = true` and `require_external_model_approval = false`. `mount --privacy automatic` alone does not turn off the approval requirement.

Agents must check this setting and obtain approval before sending real excerpts when approval is required. Start with a small preview even after opting into automatic processing.

## Troubleshooting

| Problem | Try this |
| --- | --- |
| `librarian: command not found` | Return to the checkout and run `source .venv/bin/activate`, or use its `.venv/bin/librarian` path |
| Python is too old | Check `python3 --version`; create the environment with Python 3.11 or newer |
| PDF text is missing | Install `python -m pip install -e '.[pdf]'` from the checkout; image-only scans also need [OCR](usage.md#fix-an-entry) |
| The library looks empty | Check your current directory; commands use that workspace |
| No weekly pick is ready | Add reviewed notes or resolve the index's `Next action`; see [weekly preparation](usage.md#prepare-a-weekly-pick) |
| A model command fails | Test the hook with synthetic JSON and confirm it prints only valid JSON |
| A Codex hook cannot access state or network | Keep normal Codex auth outside the repo; ask the running agent to request sandbox access for the same dry run |

Do not relocate `CODEX_HOME` into the repository to work around sandbox errors. A nested Codex hook may need access to the normal `~/.codex` state and the network; review its dry-run result before applying enrichment.

For safe automation setup, continue with [automation and delivery](automation.md). For code contributions, see [CONTRIBUTING](../CONTRIBUTING.md).
