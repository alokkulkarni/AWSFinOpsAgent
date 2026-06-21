"""Build a native .drawio network-topology diagram: nested VPC -> subnet -> instance swimlanes,
IGW/NAT icons, and peering edges. Strict XML (root cells, unique ids, escaped, no comments,
every edge carries an mxGeometry)."""
from __future__ import annotations

from devops_core.diagram.aws_shapes import icon_style
from devops_core.diagram.drawio import _esc
from devops_core.schemas.topology import Topology

ICON_W = 56
COLS = 4
COL_W = 72


def _resicon(resicon: str, fill: str = "#8C4FFF") -> str:
    return (f"sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor={fill};"
            "strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;"
            f"html=1;fontSize=10;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{resicon};")


def build_topology_drawio(topo: Topology) -> str:
    cells: list[str] = []
    nid = 1

    def nx() -> str:
        nonlocal nid
        nid += 1
        return f"t{nid}"

    title = nx()
    tt = (f"Network topology — {topo.region}  ({len(topo.vpcs)} VPCs, "
          f"{topo.subnet_count} subnets, {topo.instance_count} instances)")
    cells.append(
        f'<mxCell id="{title}" value="{_esc(tt)}" style="text;html=1;fontSize=18;fontStyle=1;'
        'align=left;" vertex="1" parent="1">'
        '<mxGeometry x="40" y="16" width="1000" height="30" as="geometry"/></mxCell>'
    )

    sub_w = COLS * COL_W + 30
    vpc_cell: dict = {}
    y = 60
    for vpc in topo.vpcs:
        sub_heights = [36 + max(1, (len(s.instances) + COLS - 1) // COLS) * COL_W + 14
                       for s in vpc.subnets]
        igw_row = 56 if (vpc.igw or vpc.nats) else 0
        body_h = sum(h + 16 for h in sub_heights) if vpc.subnets else 50
        vpc_h = 34 + igw_row + body_h + 18
        vpc_w = sub_w + 40
        vid = nx()
        vpc_cell[vpc.id] = vid
        label = "VPC " + vpc.id + (f"  {vpc.cidr}" if vpc.cidr else "") + (f"  ({vpc.name})" if vpc.name else "")
        cells.append(
            f'<mxCell id="{vid}" value="{_esc(label)}" style="swimlane;startSize=30;'
            'fillColor=#E6F0FA;strokeColor=#4D7FBF;html=1;fontStyle=1;fontSize=13;" '
            f'vertex="1" parent="1"><mxGeometry x="40" y="{y}" width="{vpc_w}" height="{vpc_h}" as="geometry"/></mxCell>'
        )

        ix = 16
        if vpc.igw:
            gid = nx()
            cells.append(
                f'<mxCell id="{gid}" value="{_esc("IGW " + vpc.igw)}" '
                f'style="{_resicon("internet_gateway", "#8C4FFF")}" vertex="1" parent="{vid}">'
                f'<mxGeometry x="{ix}" y="36" width="40" height="40" as="geometry"/></mxCell>')
            ix += 130
        for nat in vpc.nats:
            gid = nx()
            cells.append(
                f'<mxCell id="{gid}" value="{_esc("NAT " + nat)}" '
                f'style="{_resicon("nat_gateway", "#8C4FFF")}" vertex="1" parent="{vid}">'
                f'<mxGeometry x="{ix}" y="36" width="40" height="40" as="geometry"/></mxCell>')
            ix += 130

        sy = 34 + igw_row
        for s, sh in zip(vpc.subnets, sub_heights):
            sid = nx()
            scolor = "#E8F5E9" if s.public else "#FFF3E0"
            slabel = ("subnet " + s.id + (f"  {s.az}" if s.az else "") + (f"  {s.cidr}" if s.cidr else "")
                      + ("  [public]" if s.public else "  [private]"))
            cells.append(
                f'<mxCell id="{sid}" value="{_esc(slabel)}" style="swimlane;startSize=24;'
                f'fillColor={scolor};strokeColor=#7F8C8D;html=1;fontSize=11;" vertex="1" parent="{vid}">'
                f'<mxGeometry x="16" y="{sy}" width="{sub_w}" height="{sh}" as="geometry"/></mxCell>')
            for i, inst in enumerate(s.instances):
                col, row = i % COLS, i // COLS
                iid = nx()
                cells.append(
                    f'<mxCell id="{iid}" value="{_esc(inst.id + (" " + inst.type if inst.type else ""))}" '
                    f'style="{icon_style("ec2")}" vertex="1" parent="{sid}">'
                    f'<mxGeometry x="{10 + col * COL_W}" y="{30 + row * COL_W}" '
                    f'width="{ICON_W}" height="{ICON_W}" as="geometry"/></mxCell>')
            sy += sh + 16
        y += vpc_h + 30

    for p in topo.peerings:
        src, dst = vpc_cell.get(p.requester_vpc), vpc_cell.get(p.accepter_vpc)
        if src and dst:
            eid = nx()
            cells.append(
                f'<mxCell id="{eid}" value="{_esc("peering " + p.id)}" edge="1" parent="1" '
                f'source="{src}" target="{dst}" '
                'style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#8C4FFF;dashed=1;">'
                '<mxGeometry relative="1" as="geometry"/></mxCell>')

    return ('<mxGraphModel adaptiveColors="auto" grid="1" pageWidth="1600" pageHeight="1600">'
            '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            f'{"".join(cells)}</root></mxGraphModel>')
