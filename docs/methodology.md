# Methodology and contracts

## Financial arithmetic

Fundamentals use annual periods and USD millions in the fictional fixture dataset. Revenue growth is `(current revenue - prior revenue) / prior revenue * 100`; the two annual periods must be consecutive. Operating margin is `operating income / revenue * 100`. Debt/equity is `debt / equity`. Free cash flow is `operating cash flow - capex`. No balance-sheet or valuation forecasts are inferred. A zero denominator, missing source or nonconsecutive prior period yields a null result and an explicit reason.

Source rows must be available on or before the request's `as_of` date. Fiscal period alone does not establish availability: the SQL query filters `available_on` before selecting its latest two rows. Document eligibility also precedes TF-IDF fitting/search. Market retrieval chooses the latest eligible returned trading day; today's vendor response is not a point-in-time historical archive.

## Evidence and RAG

Evidence identifiers are deterministic SHA-256 prefixes over canonical source, payload, symbol, kind and availability date. They support citation reconciliation and deduplication; they are not signatures from the source publisher. Lexical retrieval fits word/unigram and bigram TF-IDF over eligible documents, orders by cosine relevance with deterministic ID ties, and returns at most two nonzero matches per symbol. There is no semantic embedding model or cross-encoder reranker.

Analyst findings are selected from exact retrieved document excerpts, source-backed close statements and deterministic calculation statements. The verifier rejects anything outside those allowed findings or carrying unknown citations. This intentionally constrained generation surface makes support auditable but does not independently establish the truth of a publisher's assertions. Untrusted document instructions remain quoted data and do not become tool permissions.

## Agent trajectories and memory

LangGraph executes planner → retriever → analyst → verifier. Verification failure permits one more analyst attempt with issue feedback. Exhaustion returns the rejected report and issues. Tool outages and missing evidence cannot be fixed by inventing a number. The graph recursion limit is 12; the analyst limit is two.

SQLite checkpoints hold structured request, plan, evidence, calculation, narrative, verification, tool events, trajectory and mode. State snapshots exist after graph steps and survive process closure. An explicit retrieval interrupt demonstrates reopening and resuming without repeating retrieval. Unique thread IDs prevent mixing research contexts. Resume requires matching offline/LLM mode.

## Retry and evaluation

Each tool call permits at most three attempts. Transient transport errors, provider 429/server errors and quota messages use bounded exponential backoff. Permanent authorization errors and invalid provider payloads fail immediately. The LLM adapter separately permits two schema generations, each with its own three-attempt transport budget. These finite budgets bound calls but do not guarantee a fixed monetary cost.

The 26-case offline benchmark uses independently hand-authored numerical answers. Metrics include complete-case pass rate, exact tool-set routing, acceptance/abstention agreement, valid citation references, numerical MAE/RMSE/max error, date violations and local nearest-rank p95 latency. Units differ across metrics, so aggregate MAE/RMSE are regression checks, not an economic error measure. Unit tests additionally inject invalid quotes/numbers, interruption, rate limits and malformed LLM output.

The verifier recalculates using the same financial function, which detects changed output but not a shared formula bug. Independent gold values address this. The small fictional suite is an engineering regression benchmark, not proof of LLM reasoning quality, general retrieval performance, financial decision quality or online reliability. A real evaluation should add independently sourced company data, domain-reviewed answers, disjoint question sets, model/version metadata and repeated paid-model trials.
