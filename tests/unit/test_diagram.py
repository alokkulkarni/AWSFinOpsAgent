import xml.etree.ElementTree as ET

from devops_core.diagram.drawio import build_drawio
from devops_core.diagram.svg import build_svg
from devops_core.schemas.estate import Estate, Resource

SAMPLE = Estate(
    resources=[
        Resource.from_arn("arn:aws:ec2:eu-west-2:1:instance/i-1"),
        Resource.from_arn("arn:aws:ec2:eu-west-2:1:instance/i-2"),
        Resource.from_arn("arn:aws:lambda:eu-west-2:1:function:fn"),
        Resource.from_arn("arn:aws:s3:::b1"),
    ],
    source="resource-explorer",
)


def test_drawio_is_well_formed_xml():
    xml = build_drawio(SAMPLE)
    root = ET.fromstring(xml)              # raises if not well-formed
    assert root.tag == "mxGraphModel"
    ids = [c.get("id") for c in root.iter("mxCell")]
    assert "0" in ids and "1" in ids       # required root cells
    assert len(ids) == len(set(ids))       # unique ids
    assert "<!--" not in xml               # no XML comments
    assert "mxgraph.aws4" in xml           # AWS shapes


def test_drawio_shows_services_and_counts():
    xml = build_drawio(SAMPLE)
    assert "ec2 (2)" in xml                 # ec2 count
    assert "lambda (1)" in xml
    assert "eu-west-2" in xml


def test_svg_is_valid_and_labels_regions():
    svg = build_svg(SAMPLE)
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "eu-west-2" in svg and "ec2" in svg
