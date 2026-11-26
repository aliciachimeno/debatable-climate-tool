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
            tags = [t for t in (f.get("stance"), f.get("likelihood"),
                                f.get("confidence") and f"{f['confidence']} confidence",
                                "stated as fact" if f.get("stated_as_fact") else None) if t]
            extra = f"  [{'; '.join(tags)}]" if tags else ""
            print(f"  - {f['statement']}\n    \"{f['quote']}\" ({f['document']}, {page}){extra}")
            for o in f.get("also_in", []):
                print(f"      also in {o['document']}, p.{o['pages'][0]}")
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


def cmd_export_web(args):
    from .web_export import export_web
    out = export_web(args.out)
    print(f"Site written to {out}")


def cmd_serve(args):
    import uvicorn
    uvicorn.run("climate_claims.web.app:app", host=args.host, port=args.port)


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

    s = sub.add_parser("export-web", help="build the static site (docs/) for GitHub Pages from the index")
    s.add_argument("--out", default=None, help=f"site folder (default: {settings.web_dir})")
    s.set_defaults(func=cmd_export_web)

    s = sub.add_parser("serve", help="start the web interface")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    from .llm import LLMError
    try:
        args.func(args)
    except LLMError as e:
        sys.exit(f"{e}\nCheck LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY and LLM_MODEL (see .env.example).")


if __name__ == "__main__":
    main()
