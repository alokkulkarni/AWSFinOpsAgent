"""`draw_diagram` tool — diagram-on-request for the DevOps agent.

Shares the agent's EstateIndex so data-driven diagrams reuse the already-scanned estate (no
rescan). Records the rendered artifact in the diagram registry for the dashboard to display, and
returns only a compact, token-light summary to the LLM (the SVG blob never round-trips the model).
"""
from __future__ import annotations

from typing import Optional

from devops_core.discovery.index import EstateIndex


def build_diagram_tools(session=None, cfg=None, index: Optional[EstateIndex] = None,
                        out_dir: str = "diagrams/agent"):
    from strands import tool

    index = index or EstateIndex(session, cfg)

    @tool
    def draw_diagram(scope: str = "", drawio_xml: str = "", description: str = "",
                     region: str = "", name: str = "diagram") -> dict:
        """Create an AWS architecture diagram (native draw.io / AWS icons) and render it as SVG/PNG,
        shown to the user and downloadable. Two modes:

        • Data-driven (from the REAL scanned estate) — set `scope` to one of:
          'estate' | 'topology' | 'vpc:<vpc-id>' | 'account:<account-id>' | 'service:<svc>'.
          'topology'/'vpc:' also need `region`. Use for "draw my estate / network / VPC / account".
        • Freeform — author valid draw.io mxGraphModel XML using AWS4 shapes
          (style 'shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.<service>') and pass it as
          `drawio_xml`. Use when the user describes an architecture to draw.

        `name` labels the output file. Returns where it was written; the image renders in the UI."""
        from devops_core.diagram import registry
        from devops_core.diagram.builder import create_diagram_artifact

        estate = None
        if scope and not drawio_xml and not scope.startswith(("topology", "vpc")):
            try:
                estate = index.estate()
            except Exception:
                estate = None
        artifact = create_diagram_artifact(
            scope=scope, drawio_xml=drawio_xml, description=description, region=region,
            name=name, out_dir=out_dir, estate=estate, session=session, cfg=cfg)
        registry.record_diagram(artifact)
        return {k: artifact.get(k) for k in ("ok", "kind", "scope", "drawio", "svg", "png", "error")}

    return [draw_diagram]
