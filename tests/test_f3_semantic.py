"""F3 acceptance without AI: the question catalogue answers every golden and demo question correctly,
and the keyword matcher routes reworded questions to the right catalogue entry.

Build-plan bar was ">= 13 of 15 golden questions correct". Here all 15 must be correct, plus D01-D03.
"""
import json
import sys

import duckdb
import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
import local_duckdb as L  # noqa: E402
from semantic.catalog import headline, load_catalog, run_question  # noqa: E402
from semantic.matcher import Matcher  # noqa: E402

CATALOG = load_catalog()


@pytest.fixture(scope="module")
def env(small_data):
    out, _ = small_data
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    L.load_bronze(con, out)
    L.run_silver(con)
    L.run_gold(con)
    L.run_semantic(con)
    golden = {q["id"]: q["answer"] for q in json.loads((out / "ground_truth" / "golden_answers.json").read_text())["questions"]}
    demo = {q["id"]: q["answer"] for q in json.loads((out / "ground_truth" / "demo_answers.json").read_text())["questions"]}
    return L.executor(con), golden, demo, con


def _close(have, want, tol_pct=None):
    if isinstance(want, str):
        return str(have).upper() == want.upper()
    if tol_pct is not None:
        return abs(float(have) - want) / want * 100 <= tol_pct
    return abs(float(have) - float(want)) < 0.006


def check_question(q, df, golden, demo):
    """Return a list of failure messages for one catalogue question."""
    fails = []
    for c in q.get("checks", []):
        if "golden" in c:
            want = golden[q["id"]][c["golden"]]
            if "list_key" in c:                                   # ranked lists: G05, G13
                (col_df, col_truth), = c["match_on"].items()
                for i, item in enumerate(want):
                    row = df.iloc[i]
                    if not (_close(row[col_df], item[col_truth]) and _close(row[c["column"]], item[c["list_key"]])):
                        fails.append(f"{q['id']} rank {i + 1}: got {row[col_df]}={row[c['column']]}, want {item}")
                continue
            rows = df
            for k, v in c.get("where", {}).items():
                rows = rows[rows[k] == v]
            have = rows.iloc[0][c["column"]]
            if not _close(have, want, c.get("tolerance_pct")):
                fails.append(f"{q['id']} {c['golden']}: got {have}, want {want}")
        elif "demo" in c:
            want = demo[q["id"]][c["demo"]]
            if c.get("row_count"):
                have = len(df)
            else:
                rows = df
                for k, v in c["count_where"].items():
                    rows = rows[rows[k] == v]
                have = len(rows)
            if have != want:
                fails.append(f"{q['id']} {c['demo']}: got {have}, want {want}")
        elif c.get("demo_d05_top"):
            if df.iloc[0]["customer"].upper() != demo["D05"]["name"].upper():
                fails.append(f"{q['id']}: top of queue {df.iloc[0]['customer']}, want {demo['D05']['name']}")
    return fails


@pytest.mark.parametrize("q", CATALOG, ids=[q["id"] for q in CATALOG])
def test_catalogue_question_matches_ground_truth(env, q):
    execute, golden, demo, _ = env
    df = run_question(q, execute)
    assert len(df) > 0
    assert not check_question(q, df, golden, demo)
    assert headline(q, df) != q["question"], "headline template did not fill"


def test_every_golden_question_is_in_the_catalogue():
    ids = {q["id"] for q in CATALOG}
    assert {f"G{i:02d}" for i in range(1, 16)} <= ids


def test_catalogue_table_in_snowflake_matches_yaml(env):
    *_, con = env
    n, = con.execute("SELECT COUNT(*) FROM semantic.QUESTION_CATALOG").fetchone()
    assert n == len(CATALOG)


def _accuracy(path):
    m = Matcher(CATALOG)
    p = yaml.safe_load((REPO / "tests" / "data" / path).read_text())
    results = [(qid, t, m.match(t)[0]) for qid, items in p.items() for t in items]
    wrong = [(qid, t, got) for qid, t, got in results if got != (None if qid == "NONE" else qid)]
    confidently_wrong = [w for w in wrong if w[2] is not None]
    return len(results), wrong, confidently_wrong


def test_matcher_on_tuning_paraphrases():
    n, wrong, _ = _accuracy("paraphrases.yaml")
    assert not wrong, wrong


def test_matcher_on_holdout_paraphrases_never_confidently_wrong():
    """Holdout rewordings were never used for tuning. A miss is acceptable only if the matcher is not
    confident (the app then asks the user to pick); a confident wrong answer is not."""
    n, wrong, confidently_wrong = _accuracy("paraphrases_holdout.yaml")
    assert not confidently_wrong, confidently_wrong
    assert (n - len(wrong)) / n >= 0.9


def test_off_topic_questions_are_not_matched():
    m = Matcher(CATALOG)
    for t in ["What is the weather in Pune?", "Write a poem", "What is the capital of France?"]:
        assert m.match(t)[0] is None, t
