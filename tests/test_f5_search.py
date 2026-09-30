"""F5 acceptance without AI: keyword (BM25) search over policy sections, investigator notes and KYC
summaries, every hit with a citation. Evaluation queries in tests/data/search_eval.yaml were written
before the search was run.
"""
import sys

import duckdb
import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import local_duckdb as L  # noqa: E402
from search.extract_policy import extract  # noqa: E402
from search.search import search, stem, terms  # noqa: E402

EVAL = yaml.safe_load((REPO / "tests" / "data" / "search_eval.yaml").read_text())["policy"]


@pytest.fixture(scope="module")
def env(small_data):
    out, _ = small_data
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    L.load_bronze(con, out)
    L.run_silver(con)
    L.run_search(con)
    return L.executor(con), con, out


def test_policy_pdf_splits_into_sections_with_pages(small_data):
    out, _ = small_data
    chunks = extract(out / "documents" / "bsa_aml_policy.pdf")
    by = {c["section"]: c for c in chunks}
    assert by["4.2 Aggregation"]["page"] == 3
    assert "Core A and on Core B" in by["4.2 Aggregation"]["text"]
    assert len(chunks) >= 25


def test_generated_policy_sql_matches_the_pdf(small_data):
    """The committed 50_policy_chunks.sql must be regenerated whenever the policy PDF changes."""
    out, _ = small_data
    from search.extract_policy import render
    committed = (REPO / "sql" / "50_search" / "50_policy_chunks.sql").read_text()
    assert render(extract(out / "documents" / "bsa_aml_policy.pdf")) == committed


def test_d04_aggregation_question_cites_section_4_2_page_3(env):
    execute, *_ = env
    d04 = next(e for e in EVAL if e.get("id") == "D04")
    _, hits = search(d04["query"], execute, k=3)            # all document types
    top = hits.iloc[0]
    assert (top.doc_type, top.section, top.page) == ("POLICY", "4.2 Aggregation", 3)
    assert "page 3" in top.citation and "4.2 Aggregation" in top.citation
    assert "aggregation" in top.snippet.lower()


def test_policy_eval_top1(env):
    """10 of 12 on the first honest run; the two misses are documented in search/README.md."""
    execute, *_ = env
    ok = 0
    for e in EVAL:
        _, h = search(e["query"], execute, k=1, doc_types=["POLICY"])
        ok += h.iloc[0]["section"] == e["section"] and int(h.iloc[0]["page"]) == e["page"]
    assert ok >= 10


def test_policy_eval_top3(env):
    execute, *_ = env
    ok = sum(e["section"] in list(search(e["query"], execute, k=3, doc_types=["POLICY"])[1]["section"]) for e in EVAL)
    assert ok >= 11


def test_every_hit_has_a_citation_and_lineage(env):
    execute, *_ = env
    _, h = search("cash deposits wire KYC review alert", execute, k=20)
    assert h.citation.notna().all() and h.source_file.notna().all()
    notes = h[h.doc_type != "POLICY"]
    assert notes.source_row.notna().all()


def test_notes_and_kyc_link_to_customers(env):
    _, con, _ = env
    rows = con.execute("SELECT doc_type, COUNT(*), COUNT(party_id) FROM search.DOC_CHUNK "
                       "WHERE doc_type <> 'POLICY' GROUP BY 1").fetchall()
    for doc_type, n, linked in rows:
        assert linked == n, doc_type


def test_party_filter_returns_only_that_customer(env):
    execute, con, _ = env
    pid = con.execute("SELECT party_id FROM search.DOC_CHUNK WHERE doc_type = 'NOTE' LIMIT 1").fetchone()[0]
    _, h = search("alert review cash", execute, k=50, party_id=pid)
    assert len(h) and set(h.party_id) == {pid}


def test_query_terms_are_sanitised():
    assert terms("'; DROP TABLE x; --") == ["drop", "table"]
    with pytest.raises(ValueError):
        from search.search import _filters
        _filters(party_id="x' OR 1=1 --")


def test_stemmer():
    assert stem("aggregating") == stem("aggregation") == "aggreg"
    assert stem("cores") == "core" and stem("filed") == "fil" and stem("policies") == "policy"
