# Mounting Librarian

Mounting means attaching this repo to a user's local reading workflow.

The goal is to configure local ignored state, not to change the public project shape. Keep the repo flat, private reading files in `library/`, and generated state in `_state/` or `_output/`.

## Agent Protocol

When an agent is asked to set up this project for a new user:

1. Run `librarian mount --check`.
2. Report the detected Python, PDF parser, model CLIs, recommended `model_command`, and digest command.
3. Ask only for choices that cannot be inferred safely.
4. Preview with `librarian mount ...` before writing config.
5. Write config only with `librarian mount --apply ...`.
6. Run `librarian lint` after mounting.

Do not ingest files, enrich entries, create automations, or send email during mount unless the user explicitly asks for that separate action.

If model enrichment is desired, set up a provider-specific local hook after mount. Keep that hook in ignored local state such as `_state/model-enrich-local`, not in the public repo.

## User Choices

Privacy mode:

- `local`: no catalog lookup, no model enrichment, no email.
- `assisted`: configure a model command if available, but only use it when the user runs `--enrich` or `librarian enrich`.
- `automatic`: configure a model command and enable enrichment during ingest/reindex/maintain.

Model mode:

- `auto`: detect model CLIs and report them, but do not choose a provider-specific command.
- `codex`: verify Codex CLI exists; still requires a JSON-compatible `--model-command`.
- `custom`: use the command provided with `--model-command`.
- `none`: disable model enrichment.

Digest mode:

- `none`: do not recommend a digest command.
- `notify`: preview weekly digest notification with no writes.
- `apply`: write weekly digest draft and sent state.
- `email`: send weekly digest email only if environment variables are configured.

## Examples

Read-only inspection:

```bash
librarian mount --check
```

Preview a local-only config:

```bash
librarian mount --privacy local --model none
```

Preview a detected-provider setup without selecting a model command:

```bash
librarian mount --privacy assisted --model auto
```

Write a custom model command:

```bash
librarian mount --privacy assisted --model custom --model-command "claude enrich-json" --apply
```

The public repo intentionally does not ship separate adapters for Codex, Claude, OpenAI, Ollama, or other providers. A user's configured `model_command` is the provider-specific layer.

Automation should prefer `librarian daily` and `librarian weekly` instead of stitching together lower-level commands.

## Local Model Hook Setup

Agents should create a local hook only after the user chooses a provider or asks for model enrichment.

The hook may be a shell script, Python script, local binary, or model CLI wrapper. It must:

- read JSON from stdin
- send only the needed metadata and text excerpt to the chosen model
- print only valid enrichment JSON to stdout
- keep provider credentials and implementation details out of the public repo

Recommended local path:

```text
_state/model-enrich-local
```

Configure it with:

```toml
[behavior]
use_model_assistance = false
model_command = ["_state/model-enrich-local"]
model_max_input_chars = 12000
require_external_model_approval = true
```

Before using real library files, test the hook with synthetic text:

```bash
printf '%s' '{"work":{"title":"Synthetic Test","author":"Example, Ada","year":"2026","work_type":"essay"},"text_excerpt":"This synthetic essay says reading systems should reduce friction while preserving judgment and privacy."}' \
  | _state/model-enrich-local
```

Expected output shape:

```json
{
  "summary": "A concise, specific summary.",
  "primer_prompts": ["A specific question.", "Another specific question."],
  "tags": ["reading"],
  "related": "None."
}
```

After the synthetic test passes, check `require_external_model_approval` before sending excerpts from real library files to any external model provider.

- `true` or missing: ask the user for explicit approval before each new real-file enrichment batch.
- `false`: the user has opted into external model enrichment for the configured `model_command`; still use dry-run review before broad batches.

## Safety

`mount` writes only `_state/config.toml`, and only with `--apply`.

Model enrichment can send title, author, filename, and text excerpts to the configured model provider. Keep `assisted` as the default unless the user deliberately chooses automatic enrichment.
