# Operations and source adapters

## Local lifecycle

Install pinned Python 3.12 dependencies, run the benchmark and tests, then generate a CLI report. Runtime directories contain trusted local state and are ignored by Git. Close engines through the composition root/context manager so HTTP clients and SQLite connections are released. Persistent CLI threads can be inspected and resumed across process restarts.

The API deliberately exposes offline mode only. Set a random ASCII `FINAGENT_API_KEY` of at least 16 characters. Start a single Uvicorn worker or the supplied Compose service. The process lock serializes access to the one checkpoint connection. The container needs a writable `/data` volume for SQLite and fixture initialization; its root filesystem can remain read-only. Back up the entire data directory consistently while the application is stopped, and restore into a separate validation instance before switching traffic.

## Bring your own sources

Provide all three files in a chosen runtime directory before creating the engine. The fixture initializer only creates missing files, so an incomplete source directory can mix custom and fictional inputs; validate every input file and its provenance explicitly.

`fundamentals.sqlite` has a `fundamentals` table with `symbol TEXT`, `period INTEGER`, `available_on TEXT` in ISO date format, and numeric `revenue`, `operating_income`, `debt`, `equity`, `operating_cash_flow`, `capex`. The primary key is `(symbol, period)`. Use one consistent currency/unit per comparable dataset; current metric rendering assumes USD millions. Restatements require an expanded versioned source schema for true point-in-time research.

`documents.json` is an array of objects with `id`, `symbol`, `available_on`, `source` and `text`. Current retrieval treats each object as a document/excerpt; large filings require bounded ingestion/chunking and reviewed availability metadata before use.

`market.json` maps each symbol to `date` and positive `close` in the fictional USD convention. For real quotes, the CLI `--live-market` adapter instead calls Alpha Vantage. Credential/entitlement failures stay explicit. The live daily endpoint leaves currency unspecified and provides a compact window; do not assume adjusted prices or a complete historical archive.

## Trust boundaries and monitoring

SQL parameters are bound and connections are read-only. The planner cannot execute arbitrary SQL or shell code. However, local databases/checkpoints/documents are trusted application inputs; their storage needs access controls and backups. SQLite memory is plaintext. Evidence hashes provide reconciliation, not external authenticity.

The shared API key gives access to all research threads and is not tenant isolation. A real deployment needs TLS, identity-aware authorization, quotas, per-tenant storage, audit retention and a scalable checkpoint backend. Expose `/health` for readiness; monitor structured verification issues and tool events for missing sources, rejected findings and exhausted retries. Local latency reports are not a capacity target. API requests do not automatically enable paid providers.

Secret values are never deliberately included in graph state or benchmark reports. Avoid dumping environment variables, raw provider exception URLs or populated `.env` files. LLM requests send selected research context to the configured provider; use only data you are authorized to send. Token counters describe returned usage, not a billing reconciliation service.
