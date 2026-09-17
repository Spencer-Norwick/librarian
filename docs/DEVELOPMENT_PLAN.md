# Public alpha readiness plan

Status: implementation and local validation complete; GitHub delivery is in progress. Routine completion includes a checked, merged pull request; independent human usability testing and a versioned release are separate steps.

## Scope and safeguards

Consolidate the existing work and make a fresh installation usable. Keep the flat-file architecture, dry-run defaults, explicit external-service consent, and no-overwrite file operations. Development and integration checks use temporary synthetic libraries, never the owner's inbox, reading files, configuration, or delivery endpoints. No production delivery, automatic deletion, history rewriting, or versioned release is part of validation. Push and merge the reviewed code through GitHub after checks pass.

## Ordered work

1. **Integrated: existing branches.** Preserve the safety/metadata repairs, readable help, and short-reading selection. Acceptance: the combined regression suite passes, all commands appear in help, and the merge diff retains both branches' behavior. Combined baseline: 107 tests and 15 subtests passed.
2. **Fix packaged setup.** Bundle initialization templates and test a built distribution in a clean environment. Acceptance: installed commands work without a source checkout; setup creates a usable workspace without requiring an external provider.
3. **Improve onboarding and release guidance.** Explain installation, project-directory behavior, optional dependencies, model consent and weekly prerequisites; provide a synthetic first-run walkthrough, contribution/security guidance, and alpha release notes. Acceptance: instructions match actual commands and declare platform/service boundaries.
4. **Verified independently.** Review the merged implementation for data-loss/privacy/delivery regressions, restore clean-checkout CI, scan tracked content and history, and exercise the documented workflow. Acceptance: meaningful regression tests and package/workflow checks pass; any limits are recorded explicitly.
5. **Prepare the handoff.** Review complete diffs, make coherent commits, update project state, and report evidence. Push the reviewed branch, merge its pull request after checks pass, verify the remote default branch, and synchronize the local default branch. Independent human usability testing and versioned release publication remain separate follow-up steps.

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
- A clean, committed, pushed and merged development branch plus public PR/commit links and a concise handoff describe remaining versioned release actions.

## Final evidence

124 tests and 19 subtests pass, including from a clean committed export. Both distribution archives pass member checks and the installed wheel completes the provider-free workflow after the build checkout is removed. The documented local-hook walkthrough also passes. Historical scanning found no secrets in 203 text blobs. Remote CI is required before merge. Live service integrations, independent human usability testing, and versioned release publication are not claimed; see `PROJECT_STATE.md` and `release.md`.
