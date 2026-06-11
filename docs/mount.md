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

## Safety

`mount` writes only `_state/config.toml`, and only with `--apply`.

Model enrichment can send title, author, filename, and text excerpts to the configured model provider. Keep `assisted` as the default unless the user deliberately chooses automatic enrichment.
