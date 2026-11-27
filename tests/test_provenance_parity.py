"""The browser port (web/static/js/provenance.js) must give exactly what provenance/chain.py gives."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from climate_claims import sources
from climate_claims.provenance import ProvenanceIndex, build_from_rows
from test_provenance import DOC, SOURCES, chapter_rows

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
SCRIPT = Path(__file__).parent / "web" / "provenance_parity.mjs"


def test_js_matches_python(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "_load", lambda: SOURCES)
    data = build_from_rows({DOC: chapter_rows()})
    spans = [[DOC, 0, 0], [DOC, 1, 1], [DOC, 1, 3], [DOC, 2, 2], [DOC, 0, 20], ["missing.pdf", 0, 3]]
    expected = [ProvenanceIndex(data).for_span(*s) if s[0] == DOC else None for s in spans]
    files = {"prov.json": data, "sources.json": SOURCES, "spans.json": spans}
    for name, content in files.items():
        (tmp_path / name).write_text(json.dumps(content), encoding="utf-8")
    out = subprocess.run(["node", str(SCRIPT), *(str(tmp_path / n) for n in files)],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == expected
    assert any(expected), "the parity cases must include real chains"
