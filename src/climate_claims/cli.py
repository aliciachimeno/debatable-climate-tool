import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from .config import settings


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def _new_run_dir(claim: str) -> Path:
    d = settings.runs_dir / f"{date.today():%Y-%m-%d}_{_slug(claim)}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _print_evidence(result: dict) -> None:
    for e in result["evidence"]:
        print(f"\n[{e['about']}] {e['query']}")
        for f in e["findings"]:
            p = f["pages"]
            page = f"p.{p[0]}" if len(p) == 1 else f"pp.{p[0]}-{p[-1]}"
            print(f"  - {f['statement']}\n    \"{f['quote']}\" ({f['document']}, {page})")
        if e.get("error"):
            print(f"  (model error: {e['error']})")
        elif not e["findings"]:
            print("  (no verified evidence in the indexed documents)")


# ---- commands ----
def cmd_index(args):
    from .indexing.build import build_index
    build_index(rebuild=args.rebuild)


def cmd_check(args):
    from .indexing.check import check_index
    check_index()


def cmd_analyze(args):
    from .analysis.analyze import analyze
    analysis = analyze(args.claim)
    out = _new_run_dir(args.claim) / "analysis.json"
    _write(out, analysis.to_dict())
    print(json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False))
    print(f"\nSaved: {out}", file=sys.stderr)


def cmd_evidence(args):
    from .evidence.pipeline import run_evidence
    from .schemas import Analysis
    path = Path(args.analysis)
    result = run_evidence(Analysis.from_dict(json.loads(path.read_text(encoding="utf-8"))))
    out = path.with_name("evidence.json")
    _write(out, result)
    _print_evidence(result)
    print(f"\nSaved: {out}", file=sys.stderr)


def cmd_run(args):
    from .analysis.analyze import analyze
    from .evidence.pipeline import run_evidence
    run_dir = _new_run_dir(args.claim)
    analysis = analyze(args.claim)
    _write(run_dir / "analysis.json", analysis.to_dict())
    result = run_evidence(analysis)
    _write(run_dir / "evidence.json", result)
    _print_evidence(result)
    print(f"\nSaved in: {run_dir}", file=sys.stderr)


def main(argv=None):
    p = argparse.ArgumentParser(prog="claims", description="Climate claim analysis with verified evidence")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("index", help="index PDFs in data/raw")
    s.add_argument("--rebuild", action="store_true", help="wipe and re-index everything")
    s.set_defaults(func=cmd_index)

    sub.add_parser("check-index", help="verify the index is consistent").set_defaults(func=cmd_check)

    s = sub.add_parser("analyze", help="analyze a claim (pipeline 1)")
    s.add_argument("claim")
    s.set_defaults(func=cmd_analyze)

    s = sub.add_parser("evidence", help="find evidence for a saved analysis.json (pipeline 2)")
    s.add_argument("analysis")
    s.set_defaults(func=cmd_evidence)

    s = sub.add_parser("run", help="analyze + evidence in one go")
    s.add_argument("claim")
    s.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()