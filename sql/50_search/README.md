# search: document search with citations, without AI (F5)

The build plan used Cortex Search. Without AI, F5 is keyword search with BM25 scoring, written as plain SQL.

| Part | File | What it does |
| --- | --- | --- |
| Policy extraction | `search/extract_policy.py` -> `sql/50_search/50_policy_chunks.sql` | Splits the policy PDF into its numbered sections (32), keeping the page each starts on. Runs locally with pypdf because Snowflake's document parsing is a Cortex AI feature |
| Search table | `sql/50_search/51_doc_chunk.sql` | `SEARCH.DOC_CHUNK`: 32 policy sections + 2,873 investigator notes + 2,541 KYC summaries, each with a citation, customer (`party_id`) and source row |
| Search | `search/search.py` | Query -> terms (stop words dropped, light suffix stripping) -> BM25 score in SQL -> top hits with citation and best-matching sentence |

Try it: `python -m search.search "what does the policy say about aggregating cash across cores" --type POLICY`

## Results (queries in `tests/data/search_eval.yaml`, written before the first run)

| Measure | Result |
| --- | --- |
| D04 "What does our BSA policy say about aggregating cash transactions across the two cores?" | Top hit: **section 4.2 Aggregation, page 3** (searching all 5,446 documents) |
| 12 policy questions, correct section first | **10 of 12** |
| 12 policy questions, correct section in top 3 | 11 of 12 |
| Notes and KYC summaries linked to a customer | 100% |

The two misses, both left unfixed so the figure stays honest:
- "When must a SAR be filed?" returns 7.1 *When to file* before 7.2 *Deadline*. The question is ambiguous; 7.2 is second.
- "Can we tell a customer that a SAR was filed about them?" misses 7.4 *Confidentiality*, which says the SAR "must never be disclosed to the subject". No words overlap. This is the known limit of keyword search: it finds words, not meaning. A reviewed synonym list is the non-AI remedy.

One change was made after the first run: modal verbs (must, shall, may, will) became stop words.
