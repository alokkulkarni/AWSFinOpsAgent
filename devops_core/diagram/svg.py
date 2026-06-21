"""Self-contained SVG estate overview — always renders (no draw.io/Graphviz needed), so the
dashboard can show an image. The .drawio file remains the AWS-icon source of truth."""
from __future__ import annotations

from devops_core.diagram.aws_shapes import fill_color
from devops_core.diagram.drawio import _group_counts
from devops_core.schemas.estate import Estate


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_svg(estate: Estate, group_by: str = "region", cols: int = 6) -> str:
    groups = _group_counts(estate, group_by)
    tile_w, tile_h, gap, pad = 150, 56, 14, 24
    title_h, sec_head = 44, 34

    parts: list[str] = []
    y = title_h + 16
    width = pad * 2 + cols * (tile_w + gap)

    for grp, services in sorted(groups.items(), key=lambda kv: -sum(kv[1].values())):
        items = sorted(services.items(), key=lambda kv: -kv[1])
        rows = max(1, (len(items) + cols - 1) // cols)
        total = sum(services.values())
        parts.append(f'<text x="{pad}" y="{y + 22}" font-size="16" font-weight="bold" '
                     f'fill="#232F3E">{_esc(grp)}  ({total})</text>')
        y += sec_head
        for i, (svc, cnt) in enumerate(items):
            col, row = i % cols, i // cols
            x = pad + col * (tile_w + gap)
            ty = y + row * (tile_h + gap)
            parts.append(
                f'<rect x="{x}" y="{ty}" width="{tile_w}" height="{tile_h}" rx="6" '
                f'fill="{fill_color(svc)}" opacity="0.92"/>'
                f'<text x="{x + 10}" y="{ty + 23}" font-size="13" font-weight="bold" '
                f'fill="#ffffff">{_esc(svc)}</text>'
                f'<text x="{x + 10}" y="{ty + 43}" font-size="12" fill="#ffffff">{cnt}</text>'
            )
        y += rows * (tile_h + gap) + 10

    height = y + pad
    title = f"AWS Estate — {len(estate.resources)} resources · {len(estate.regions)} region(s) · [{estate.source}]"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica,Arial,sans-serif">'
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
        f'<text x="{pad}" y="30" font-size="20" font-weight="bold" fill="#232F3E">{_esc(title)}</text>'
        f'{"".join(parts)}</svg>'
    )
