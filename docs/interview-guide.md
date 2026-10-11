# Interview walkthrough

1. Draw the four-node LangGraph state machine. Explain the difference between role decomposition and four independent LLMs.
2. Show a planner-selected SQL/document/market tool set and explain how the schema bounds executable operations.
3. Derive all four financial formulas and explain zero denominators, units, fiscal periods and publication dates.
4. Demonstrate a retrieval interrupt, close the process, inspect SQLite-backed state and resume at the analyst.
5. Explain why unique thread IDs and mode checks prevent context mixing, and why this deployment uses one worker.
6. Show why symbol/date filtering happens before document index fitting. Discuss TF-IDF limitations and a future dense retrieval alternative.
7. Inject a false number and a fabricated citation. Show independent verifier rejection and bounded analyst repair.
8. Explain the limit of exact source quotes: citation support does not prove the underlying publisher assertion is true.
9. Simulate 429, provider quota JSON, invalid prices and incomplete LLM output. Distinguish transport retries from schema repair.
10. Explain JSON mode versus provider-enforced JSON Schema, and why local Pydantic validation remains necessary here.
11. Discuss the shared calculation function's limitation and how independently authored gold answers detect formula errors.
12. Walk through benchmark arithmetic, routing, abstention and temporal metrics. Explain why offline fixture success is not a live LLM accuracy claim.
13. Show Protocol-based adapters, dependency injection, app-factory resource ownership and the immutable retry policy.
14. Discuss point-in-time data revisions, market currency, exposure of research data to paid providers, and requirements for tenant-aware production deployment.
