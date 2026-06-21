"""Build a native .drawio (mxGraphModel) estate diagram with AWS icons.

Layout: a swimlane container per region (or account/region), filled with AWS service-icon tiles
labelled "<service> (<count>)". Strict XML: root cells 0/1, unique ids, escaped text, no comments,
every edge carries an mxGeometry. (Topology edges land in a later phase.)
"""
from __future__ import annotations

from devops_core.diagram.aws_shapes import icon_style
from devops_core.schemas.estate import Estate


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _group_counts(estate: Estate, group: str) -> dict:
    """{group_value: {service: count}} where group is 'region' or 'account'."""
    out: dict = {}
    for r in estate.resources:
        g = (getattr(r, group) or ("global" if group == "region" else "?"))
        out.setdefault(g, {}).setdefault(r.service, 0)
        out[g][r.service] += 1
    return out


def build_drawio(estate: Estate, group_by: str = "region", cols: int = 8) -> str:
    groups = _group_counts(estate, group_by)
    cells: list[str] = []
    nid = 1

    def new_id() -> str:
        nonlocal nid
        nid += 1
        return f"n{nid}"

    title = new_id()
    title_text = (f"AWS Estate — {len(estate.resources)} resources, "
                  f"{len(estate.regions)} region(s)  [{estate.source}]")
    cells.append(
        f'<mxCell id="{title}" value="{_esc(title_text)}" '
        'style="text;html=1;fontSize=18;fontStyle=1;align=left;verticalAlign=middle;" '
        'vertex="1" parent="1"><mxGeometry x="40" y="16" width="900" height="30" as="geometry"/></mxCell>'
    )

    icon_w, label_h, gap, pad_x, pad_top = 78, 30, 26, 20, 40
    cell_w = icon_w + gap
    y = 60
    for grp, services in sorted(groups.items(), key=lambda kv: -sum(kv[1].values())):
        items = sorted(services.items(), key=lambda kv: -kv[1])
        rows = max(1, (len(items) + cols - 1) // cols)
        cw = cols * cell_w + pad_x
        ch = pad_top + rows * (icon_w + label_h + 14) + pad_x
        cid = new_id()
        total = sum(services.values())
        cells.append(
            f'<mxCell id="{cid}" value="{_esc(f"{grp}  ({total} resources)")}" '
            'style="swimlane;startSize=28;fillColor=#F2F3F3;strokeColor=#879196;html=1;'
            'fontStyle=1;fontSize=13;" vertex="1" parent="1">'
            f'<mxGeometry x="40" y="{y}" width="{cw}" height="{ch}" as="geometry"/></mxCell>'
        )
        for i, (svc, cnt) in enumerate(items):
            col, row = i % cols, i // cols
            x = pad_x + col * cell_w
            yy = pad_top + row * (icon_w + label_h + 14)
            iid = new_id()
            cells.append(
                f'<mxCell id="{iid}" value="{_esc(f"{svc} ({cnt})")}" style="{icon_style(svc)}" '
                f'vertex="1" parent="{cid}">'
                f'<mxGeometry x="{x}" y="{yy}" width="{icon_w}" height="{icon_w}" as="geometry"/></mxCell>'
            )
        y += ch + 30

    body = "".join(cells)
    return (
        '<mxGraphModel adaptiveColors="auto" grid="1" pageWidth="1600" pageHeight="1200">'
        '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
        f'{body}</root></mxGraphModel>'
    )
