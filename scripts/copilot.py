"""Ask the risk copilot anything, from the command line. One entry point for every tool. No AI.

  python scripts/copilot.py "How many alerts did we get last month?"
  python scripts/copilot.py "What does our policy say about aggregating cash across the two cores?"
  python scripts/copilot.py "Tell me about Deborah Sanford"
  python scripts/copilot.py --no-log "..."          # do not write to AUDIT.QUESTION_LOG

The router picks the tool (reviewed question, document search or customer view) and says which rule
chose it. Every question is logged to AUDIT.QUESTION_LOG unless --no-log is given.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from agent.answer import answer, log_question  # noqa: E402
from scripts.ask import snowflake_executor  # noqa: E402
from semantic.catalog import by_id  # noqa: E402


def show(a):
    print(f"\nQuestion : {a.question}")
    print(f"Route    : {a.route}  (rule: {a.rule})")
    if a.answered_as:
        print(f"Answered : {a.answered_as}")
    print(f"\n{a.headline}")
    if a.suggestions:
        cat = by_id()
        for qid, _ in a.suggestions:
            print(f"  {qid}  {cat[qid]['question']}")
        print("Rephrase, or run: python scripts/ask.py --id <ID>")
    with pd.option_context("display.max_columns", 20, "display.width", 180, "display.max_colwidth", 90):
        for title, df in a.tables:
            print(f"\n--- {title} ({len(df)} rows)")
            print(df.head(15).to_string(index=False))
    if a.citations:
        print("\nSources:")
        for c in a.citations[:10]:
            print(f"  - {c}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+")
    ap.add_argument("--connection", default="default")
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    execute = snowflake_executor(a.connection)
    ans = answer(" ".join(a.question), execute)
    show(ans)
    if not a.no_log:
        log_id = log_question(ans, execute)
        print(f"\nLogged to AUDIT.QUESTION_LOG ({log_id})")


if __name__ == "__main__":
    main()
