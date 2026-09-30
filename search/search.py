"""Keyword search over SEARCH.DOC_CHUNK with BM25 scoring in SQL, and citations. No AI.

  python -m search.search "what does the policy say about aggregating cash across cores" --type POLICY

How it works
  1. The query is split into terms: lower case, stop words dropped, a light suffix stripper
     ("aggregating" -> "aggreg"), so a term matches the start of any word in the document.
  2. One SQL query counts how many documents contain each term (document frequency).
  3. A second SQL query scores every document with BM25 (rarer terms and repeated terms count more,
     long documents count a little less) and returns the top k with their citations.
  4. The best-matching sentence of each hit is picked as the snippet.
Everything runs in Snowflake (or DuckDB for tests) through an `execute(sql) -> DataFrame` function.
"""
import math
import re
import sys

STOP = set("""a an the of in on at to for and or is are was were be been being do does did we our us you your
i me my what which who whom how when where why many much there this that these those with by from as it its any
all have has had can could would should please show tell give list say says said about into than then them
they their per across between after before over under more most less also only just not no yes
must shall may might will bank banks""".split())
SUFFIXES = ["ations", "ation", "ating", "ated", "ates", "ions", "ion", "ings", "ing", "ies", "ed", "es", "s"]
DOC_TYPES = {"POLICY", "NOTE", "KYC"}
K1, B = 1.2, 0.75


def stem(w):
    if w.isdigit() or w.startswith("$"):
        return w
    for suf in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            if suf == "es" and not re.search(r"(s|x|z|ch|sh)es$", w):
                return w[:-1]                      # "cores" -> "core", "boxes" -> "box"
            if suf == "ies":
                return w[:-3] + "y"
            return w[: -len(suf)]
    return w


def terms(query):
    words = re.findall(r"[a-z0-9$]+", query.lower().replace(",", ""))
    out = []
    for w in words:
        if w in STOP or len(w) < 2:
            continue
        t = stem(w)
        if t not in out:
            out.append(t)
    return out[:12]


def _filters(doc_types=None, party_id=None):
    where = []
    if doc_types:
        bad = set(doc_types) - DOC_TYPES
        if bad:
            raise ValueError(f"unknown document type {bad}")
        where.append("doc_type IN (" + ", ".join(f"'{t}'" for t in sorted(doc_types)) + ")")
    if party_id:
        if not re.fullmatch(r"PTY_[0-9a-f]{8,32}", party_id):
            raise ValueError("bad party id")
        where.append(f"party_id = '{party_id}'")
    return (" WHERE " + " AND ".join(where)) if where else ""


def build_df_sql(ts, table="SEARCH.DOC_CHUNK"):
    parts = [f"SUM(IFF(CONTAINS(search_text, ' {t}'), 1, 0)) AS df_{i}" for i, t in enumerate(ts)]
    return f"SELECT COUNT(*) AS n_docs, {', '.join(parts)} FROM {table}"


def build_search_sql(ts, idf, k=5, doc_types=None, party_id=None, table="SEARCH.DOC_CHUNK"):
    score_parts = []
    for i, t in enumerate(ts):
        tf = f"((LENGTH(search_text) - LENGTH(REPLACE(search_text, ' {t}', ''))) / {len(t) + 1})"
        score_parts.append(
            f"{idf[i]:.6f} * {tf} * {K1 + 1} / ({tf} + {K1} * ({1 - B} + {B} * LENGTH(search_text) / avg_len))")
    score = " + ".join(score_parts)
    hits = " + ".join(f"IFF(CONTAINS(search_text, ' {t}'), 1, 0)" for t in ts)
    return f"""WITH d AS (
    SELECT doc_id, doc_type, title, citation, party_id, source_system, doc_date, page, section, body,
           source_file, source_row, search_text, AVG(LENGTH(search_text)) OVER () AS avg_len
      FROM {table}{_filters(doc_types, party_id)}
)
SELECT doc_id, doc_type, title, citation, party_id, source_system, doc_date, page, section, body,
       source_file, source_row, ROUND({score}, 4) AS score, {hits} AS terms_matched
  FROM d
 WHERE {hits} > 0
 ORDER BY score DESC, doc_id
 LIMIT {int(k)}"""


def snippet(body, ts, max_len=320):
    sentences = re.split(r"(?<=[.;])\s+", body or "")
    def hits(s):
        low = " " + re.sub(r"[^a-z0-9$]+", " ", s.lower()) + " "
        return sum(1 for t in ts if " " + t in low)
    full = [x for x in sentences if len(x.split()) >= 4] or sentences
    best = max(full, key=lambda x: (hits(x), -abs(len(x) - 160))) if full else ""   # most terms, then a readable length
    return best if len(best) <= max_len else best[: max_len - 1] + "…"


def search(query, execute, k=5, doc_types=None, party_id=None, table="SEARCH.DOC_CHUNK"):
    """Return (terms, DataFrame of hits with citation and snippet). execute(sql) -> DataFrame."""
    ts = terms(query)
    if not ts:
        return ts, None
    df_row = execute(build_df_sql(ts, table))
    df_row.columns = [c.lower() for c in df_row.columns]
    n = float(df_row.iloc[0]["n_docs"])
    idf = [math.log(1 + (n - float(df_row.iloc[0][f"df_{i}"] or 0) + 0.5) / (float(df_row.iloc[0][f"df_{i}"] or 0) + 0.5))
           for i in range(len(ts))]
    hits = execute(build_search_sql(ts, idf, k, doc_types, party_id, table))
    hits.columns = [c.lower() for c in hits.columns]
    if len(hits):
        hits["snippet"] = [snippet(b, ts) for b in hits["body"]]
    return ts, hits


def main():
    import argparse
    sys.path.insert(0, ".")
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+")
    ap.add_argument("--type", action="append", choices=sorted(DOC_TYPES))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--connection", default="default")
    a = ap.parse_args()
    from scripts.ask import snowflake_executor
    ts, hits = search(" ".join(a.query), snowflake_executor(a.connection), a.k, a.type)
    print(f"terms: {ts}")
    if hits is None or not len(hits):
        print("No documents matched.")
        return
    for r in hits.itertuples():
        print(f"\n[{r.doc_type}] {r.citation}  (score {r.score})\n  {r.snippet}")


if __name__ == "__main__":
    main()
