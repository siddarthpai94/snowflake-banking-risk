"""Case narratives with four-eyes approval (F7). No AI.

  python scripts/case.py draft --customer "Deborah Sanford" --author jehal
  python scripts/case.py draft --top --author jehal              # the highest-risk customer in the queue
  python scripts/case.py list
  python scripts/case.py show <output_id>
  python scripts/case.py approve <output_id> --approver siddarth --comment "Escalate"
  python scripts/case.py reject  <output_id> --approver siddarth --comment "Needs wire detail"
  python scripts/case.py export  <output_id>                    # writes outputs/exports/<subject>_<id>.pdf and .md
  python scripts/case.py verify  <output_id>                    # re-render from the audit record and compare

The author can never approve their own output (config/bank_demo.yaml: report.approver_cannot_be_author).
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from agent.router import find_customers  # noqa: E402
from outputs import case_store as C  # noqa: E402
from outputs.export_pdf import export_pdf  # noqa: E402
from scripts.ask import snowflake_executor  # noqa: E402


def resolve_party(args, execute):
    if args.top:
        df = execute("SELECT party_id FROM GOLD.ALERT_QUEUE WHERE queue_rank = 1")
        return str(df.iloc[0, 0])
    found = find_customers(args.customer, execute)
    if not found:
        sys.exit(f"No customer named {args.customer!r} in GOLD.PARTY.")
    if len(found) > 1:
        print(f"{len(found)} customers share this name; using the one in most cores ({found[0].party_id}).")
    return found[0].party_id


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft")
    d.add_argument("--customer")
    d.add_argument("--top", action="store_true")
    d.add_argument("--author", required=True)
    sub.add_parser("list")
    for name in ("show", "export", "verify"):
        sub.add_parser(name).add_argument("output_id")
    for name in ("approve", "reject"):
        s = sub.add_parser(name)
        s.add_argument("output_id")
        s.add_argument("--approver", required=True)
        s.add_argument("--comment", default="")
    ap.add_argument("--connection", default="default")
    a = ap.parse_args()
    execute = snowflake_executor(a.connection)

    if a.cmd == "draft":
        if not a.top and not a.customer:
            ap.error("give --customer NAME or --top")
        oid, md = C.draft_narrative(resolve_party(a, execute), a.author, execute)
        print(md)
        print(f"Saved as DRAFT {oid}. Approve with: python scripts/case.py approve {oid} --approver <someone else>")
    elif a.cmd == "list":
        with pd.option_context("display.width", 180):
            print(C.list_outputs(execute).to_string(index=False))
    elif a.cmd == "show":
        md, st = C.final_text(a.output_id, execute)
        print(md)
        print(f"Status: {st}")
    elif a.cmd in ("approve", "reject"):
        try:
            st = C.decide(a.output_id, a.approver, "APPROVED" if a.cmd == "approve" else "REJECTED", execute, a.comment)
        except C.ApprovalError as e:
            sys.exit(f"Not recorded: {e}")
        print(f"{st['status']} by {st['approver']} at {st['decided_at']}")
    elif a.cmd == "export":
        md, st = C.final_text(a.output_id, execute)
        out = C.get_output(a.output_id, execute)
        folder = REPO / "outputs" / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"{str(out['subject']).replace(' ', '_').lower()}_{a.output_id[:8]}"
        (folder / f"{stem}.md").write_text(md, encoding="utf-8")
        export_pdf(md, folder / f"{stem}.pdf", status=st,
                   footer=f"Output {a.output_id} | status {st} | text SHA-256 {out['content_sha256'][:16]}... | synthetic data")
        print(f"Wrote {folder / (stem + '.pdf')} and .md (status {st})")
    elif a.cmd == "verify":
        ok, info = C.reproduce(a.output_id, execute)
        print(("REPRODUCED: " if ok else "MISMATCH: ") + str(info))


if __name__ == "__main__":
    main()
