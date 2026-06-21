"""Build resource-picker choices for the DevOps review/diagnose panel from a scanned estate.
Pure (no Streamlit) so it's unit-testable; the panel maps a chosen label back to {id, region}."""
from __future__ import annotations


def resource_choices(resources: list, service: str, limit: int = 500) -> list:
    """Picker entries for `service` from the estate's resource dicts.

    Each entry: {label, service, id, region} where `id` is the ARN (preferred — the review/diagnose
    engines infer service + name from it) or the bare id. Deduped by id, sorted by label.
    """
    out, seen = [], set()
    for r in resources:
        if r.get("service") != service:
            continue
        ident = r.get("arn") or r.get("id") or ""
        if not ident or ident in seen:
            continue
        seen.add(ident)
        name = r.get("name") or r.get("id") or ident
        out.append({"label": f'{name}  ·  {r.get("region") or "global"}',
                    "service": service, "id": ident, "region": r.get("region")})
        if len(out) >= limit:
            break
    return sorted(out, key=lambda c: c["label"].lower())
