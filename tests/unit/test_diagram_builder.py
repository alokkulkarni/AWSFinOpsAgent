"""Diagram-on-request: the builder handles freeform agent-authored XML + data-driven scopes,
and the registry hands the artifact to the dashboard. No AWS needed (estate injected)."""
from pathlib import Path

from devops_core.diagram import registry
from devops_core.diagram.builder import create_diagram_artifact, filter_estate
from devops_core.schemas.estate import Estate, Resource

EST = Estate(resources=[Resource.from_arn(a) for a in [
    "arn:aws:ec2:eu-west-2:1:instance/i-1",
    "arn:aws:ec2:us-east-1:2:instance/i-2",
    "arn:aws:lambda:eu-west-2:1:function:f",
    "arn:aws:s3:::b",
]])

VALID = ('<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
         '<mxCell id="n2" value="EC2" style="shape=mxgraph.aws4.resourceIcon" vertex="1" '
         'parent="1"><mxGeometry x="40" y="40" width="78" height="78" as="geometry"/></mxCell>'
         '</root></mxGraphModel>')


# --- freeform (agent-authored mxGraph per the draw.io skill) ---
def test_freeform_valid_writes_drawio(tmp_path):
    r = create_diagram_artifact(drawio_xml=VALID, out_dir=str(tmp_path), name="free")
    assert r["ok"] and r["kind"] == "freeform"
    assert Path(r["drawio"]).read_text() == VALID


def test_freeform_rejects_malformed_xml(tmp_path):
    r = create_diagram_artifact(drawio_xml="<mxGraphModel><root", out_dir=str(tmp_path))
    assert not r["ok"] and "xml" in r["error"].lower()


def test_freeform_rejects_non_drawio_xml(tmp_path):
    r = create_diagram_artifact(drawio_xml="<foo><bar/></foo>", out_dir=str(tmp_path))
    assert not r["ok"]


# --- data-driven (from the real scanned estate) ---
def test_data_estate_renders_svg(tmp_path):
    r = create_diagram_artifact(scope="estate", estate=EST, out_dir=str(tmp_path), name="est")
    assert r["ok"] and r["kind"] == "data"
    assert r["svg_content"] and "<svg" in r["svg_content"]
    assert Path(r["drawio"]).exists()


def test_unknown_scope_errors(tmp_path):
    r = create_diagram_artifact(scope="bogus", estate=EST, out_dir=str(tmp_path))
    assert not r["ok"]


def test_filter_by_account():
    assert filter_estate(EST, "account", "1").counts("service") == {"ec2": 1, "lambda": 1}


def test_filter_by_service():
    assert filter_estate(EST, "service", "ec2").counts("service") == {"ec2": 2}


# --- registry hands the rendered artifact to the dashboard ---
def test_registry_roundtrip():
    registry.clear()
    assert registry.last_diagram() is None
    registry.record_diagram({"ok": True, "drawio": "x.drawio"})
    assert registry.last_diagram()["drawio"] == "x.drawio"
    registry.clear()
    assert registry.last_diagram() is None
