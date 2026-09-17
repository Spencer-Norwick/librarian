# Security and privacy

Reading Librarian is public alpha software. Review previews before applying changes and keep independent backups of important readings and local state.

Local reading files and `_state/` are ignored by Git, but ignored files are not encrypted. Model hooks execute the configured command and may send metadata or text excerpts to its provider, including during dry-run enrichment. Catalog lookup sends bibliographic queries to Open Library. Delivery channels are explicitly requested; do not include credentials or recipient details in public reports.

Report security problems using the repository's private GitHub vulnerability-reporting option if available. If it is unavailable, open a minimal issue requesting a private contact channel without posting exploit details, private documents, credentials, or sensitive logs. Ordinary bugs belong in [GitHub Issues](https://github.com/Spencer-Norwick/librarian/issues) with a synthetic reproduction.

There is no formal response-time guarantee or supported stable release series yet. Security and data-integrity fixes target the current development version.
