# Public alpha readiness plan

Status: development and validation complete; independent human testing and publication remain release steps. Reviewed work is on `codex/public-alpha-readiness`.

## Scope and safeguards

Consolidate the existing work and make a fresh installation usable. Keep the flat-file architecture, dry-run defaults, explicit external-service consent, and no-overwrite file operations. Development and integration checks use temporary synthetic libraries, never the owner's inbox, reading files, configuration, or delivery endpoints. No production delivery, automatic deletion, history rewriting, or public release is part of validation.

## Ordered work

1. **Integrated: existing branches.** Preserve the safety/metadata repairs, readable help, and short-reading selection. Acceptance: the combined regression suite passes, all commands appear in help, and the merge diff retains both branches' behavior. Combined baseline: 107 tests and 15 subtests passed.
2. **Fix packaged setup.** Bundle initialization templates and test a built distribution in a clean environment. Acceptance: installed commands work without a source checkout; setup creates a usable workspace without requiring an external provider.
3. **Improve onboarding and release guidance.** Explain installation, project-directory behavior, optional dependencies, model consent and weekly prerequisites; provide a synthetic first-run walkthrough, contribution/security guidance, and alpha release notes. Acceptance: instructions match actual commands and declare platform/service boundaries.
4. **Verified independently.** Review the merged implementation for data-loss/privacy/delivery regressions, restore clean-checkout CI, scan tracked content and history, and exercise the documented workflow. Acceptance: meaningful regression tests and package/workflow checks pass; any limits are recorded explicitly.
5. **Prepare the handoff.** Review complete diffs, make coherent commits, update project state, and report evidence. Publishing and independent human testing remain explicit follow-up steps; do not claim either happened during automated development.

## Delegation

- Packaging agent: installed setup/resources and package regression tests.
- Documentation agent: README/runbooks and contribution/security/release notes.
- Independent review agent: safety/privacy/integration review and focused regression coverage; report findings to the integrator.
- Integrator: merge resolution, cross-component validation, CI, tracked-history audit, final review and commits.

## Definition of done

- Existing safety and weekly/help behaviors are retained.
- Unit/integration suite and wheel-install smoke check pass.
- A temporary synthetic ingest → enrichment → maintenance → short weekly flow passes without external delivery.
- Public docs match behavior; no real reading files or private state enter commits.
- A clean, committed development branch and concise handoff describe remaining release actions.

## Final evidence

124 tests and 19 subtests pass, including from a clean committed export. Both distribution archives pass member checks and the installed wheel completes the provider-free workflow after the build checkout is removed. The documented local-hook walkthrough also passes. Historical scanning found no secrets in 203 text blobs. Remote CI, live service integrations, independent human usability testing, and publication are not claimed; see `PROJECT_STATE.md` and `release.md`.
