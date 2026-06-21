"""Diagram-on-request builder — turns a chat request into a rendered, downloadable diagram.

Two paths (per the locked decision):
  • **data-driven** — `scope` in {estate, topology, vpc:<id>, account:<id>, service:<svc>}: build
    the `.drawio` from the REAL scanned estate/topology (reuses build_drawio/build_topology_drawio).
  • **freeform** — the agent authors valid mxGraphModel XML (AWS4 shapes, per the draw.io skill);
    we validate well-formedness, then render.

Renders `.svg` (+ `.png` when the draw.io CLI is present; build_svg fallback for data scopes) and
returns {ok, kind, scope, drawio, svg, png, svg_content, error}. Pure of Strands so it's unit-testable.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from devops_core.diagram.drawio import build_drawio
from devops_core.diagram.render import render
from devops_core.diagram.svg import build_svg
from devops_core.diagram.topology_drawio import build_topology_drawio
from devops_core.schemas.estate import Estate

_FILTER_SCOPES = {"account", "service", "region"}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", (s or "diagram").lower()).strip("-") or "diagram"


def filter_estate(estate: Estate, by: str, value: str) -> Estate:
    """Subset the estate by an attribute (account/service/region) for a scoped diagram."""
    return Estate(resources=[r for r in estate.resources if getattr(r, by, None) == value],
                  source=estate.source, notes=list(estate.notes))


def _validate_drawio_xml(xml: str) -> Optional[str]:
    """None if the string is a well-formed draw.io model, else an error message."""
    if not xml or not xml.strip():
        return "empty drawio_xml"
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return f"invalid XML: {e}"
    if root.tag in ("mxGraphModel", "mxfile") or root.find(".//mxGraphModel") is not None:
        return None
    return f"root <{root.tag}> is not a draw.io mxGraphModel/mxfile"


def _data_drawio(scope: str, estate: Optional[Estate], topology, region: str,
                 session, cfg) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (drawio_xml, svg_content, error) for a data-driven scope."""
    head, _, ident = scope.partition(":")
    head = head or "estate"

    if head in ("topology", "vpc"):
        if topology is None:
            from finops_core.config import Config
            from devops_core.discovery.topology import TopologyScanner
            cfg = cfg or Config()
            reg = region or (cfg.aws.region if getattr(cfg, "aws", None) else None)
            if not reg:
                return None, None, "topology scope needs a region"
            topology = TopologyScanner(session, cfg).scan(reg)
        if head == "vpc" and ident:
            from devops_core.schemas.topology import Topology
            topology = Topology(
                region=topology.region,
                vpcs=[v for v in topology.vpcs if v.id == ident],
                peerings=[p for p in topology.peerings
                          if ident in (p.requester_vpc, p.accepter_vpc)],
                notes=list(topology.notes))
            if not topology.vpcs:
                return None, None, f"no VPC {ident!r} in {topology.region}"
        return build_topology_drawio(topology), None, None  # svg via CLI render only

    if head in ("estate", "account", "service", "region"):
        if estate is None:
            from finops_core.discovery.engine import EstateScanner
            estate = EstateScanner(session, cfg).scan(regions=[region] if region else None)
        if head in _FILTER_SCOPES:
            if not ident:
                return None, None, f"{head} scope needs an id (e.g. {head}:<value>)"
            estate = filter_estate(estate, head, ident)
            if not estate.resources:
                return None, None, f"no resources for {head}={ident!r}"
        return build_drawio(estate), build_svg(estate), None

    return None, None, f"unknown scope {scope!r} (use estate|topology|vpc:<id>|account:<id>|service:<svc>)"


def create_diagram_artifact(*, scope: str = "", drawio_xml: str = "", description: str = "",
                            region: str = "", name: str = "diagram", out_dir: str = "diagrams/agent",
                            estate: Optional[Estate] = None, topology=None,
                            session=None, cfg=None) -> dict:
    """Build + render a diagram. Freeform when drawio_xml is given, else data-driven by scope."""
    if drawio_xml:
        kind, xml, svg_content = "freeform", drawio_xml, None
        err = _validate_drawio_xml(drawio_xml)
    else:
        kind = "data"
        xml, svg_content, err = _data_drawio((scope or "estate").strip(), estate, topology,
                                             region, session, cfg)
    if err:
        return {"ok": False, "kind": kind, "scope": scope or "freeform", "error": err}

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = out / _slug(name)
    drawio_path = base.with_suffix(".drawio")
    drawio_path.write_text(xml)

    svg_path = render(str(drawio_path), "svg")
    png_path = render(str(drawio_path), "png")
    if svg_path and not svg_content:
        try:
            svg_content = Path(svg_path).read_text()
        except OSError:
            svg_content = None

    return {"ok": True, "kind": kind, "scope": scope or "freeform", "description": description,
            "drawio": str(drawio_path), "svg": svg_path, "png": png_path,
            "svg_content": svg_content}
