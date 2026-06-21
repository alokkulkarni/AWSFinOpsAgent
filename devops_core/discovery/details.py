"""On-demand deep describe — the thin inventory (id/type/region/tags) is great for breadth, but
answering "is this ENI orphaned?", "what's attached?", "what's this SG's rules?" needs the live,
service-specific object. resource_details() fetches it for ONE resource (the drill-down), so the
agent gets complete information instead of hedging.

Dispatch covers the EC2 networking/compute family (where attachment/topology questions live) plus
Lambda and RDS; uncovered types degrade gracefully with a note. JSON-safe (datetimes → ISO).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from finops_core.aws.session import client

# resource_type -> how to describe it.
#   many:    pass the id as a single-item list (EC2 describe_* pattern), result under `key`
#   scalar:  pass the id as a string; result under `key`[0], or the response itself if no `key`
#   nested:  unwrap one level (EC2 instances live under Reservations[].Instances[])
#   use_arn: pass the ARN instead of the bare id
_DETAIL = {
    "ec2:network-interface": dict(svc="ec2", method="describe_network_interfaces",
                                  arg="NetworkInterfaceIds", key="NetworkInterfaces", many=True),
    "ec2:instance": dict(svc="ec2", method="describe_instances", arg="InstanceIds",
                         key="Reservations", many=True, nested="Instances"),
    "ec2:security-group": dict(svc="ec2", method="describe_security_groups", arg="GroupIds",
                               key="SecurityGroups", many=True),
    "ec2:subnet": dict(svc="ec2", method="describe_subnets", arg="SubnetIds", key="Subnets",
                       many=True),
    "ec2:vpc": dict(svc="ec2", method="describe_vpcs", arg="VpcIds", key="Vpcs", many=True),
    "ec2:natgateway": dict(svc="ec2", method="describe_nat_gateways", arg="NatGatewayIds",
                           key="NatGateways", many=True),
    "ec2:internet-gateway": dict(svc="ec2", method="describe_internet_gateways",
                                 arg="InternetGatewayIds", key="InternetGateways", many=True),
    "ec2:route-table": dict(svc="ec2", method="describe_route_tables", arg="RouteTableIds",
                            key="RouteTables", many=True),
    "ec2:vpc-endpoint": dict(svc="ec2", method="describe_vpc_endpoints", arg="VpcEndpointIds",
                             key="VpcEndpoints", many=True),
    "ec2:vpc-peering-connection": dict(svc="ec2", method="describe_vpc_peering_connections",
                                       arg="VpcPeeringConnectionIds", key="VpcPeeringConnections",
                                       many=True),
    "ec2:network-acl": dict(svc="ec2", method="describe_network_acls", arg="NetworkAclIds",
                            key="NetworkAcls", many=True),
    "ec2:volume": dict(svc="ec2", method="describe_volumes", arg="VolumeIds", key="Volumes",
                       many=True),
    "ec2:snapshot": dict(svc="ec2", method="describe_snapshots", arg="SnapshotIds",
                         key="Snapshots", many=True),
    "ec2:transit-gateway": dict(svc="ec2", method="describe_transit_gateways",
                                arg="TransitGatewayIds", key="TransitGateways", many=True),
    "elasticloadbalancing:loadbalancer": dict(svc="elbv2", method="describe_load_balancers",
                                              arg="LoadBalancerArns", key="LoadBalancers",
                                              many=True, use_arn=True),
    "elasticloadbalancing:targetgroup": dict(svc="elbv2", method="describe_target_groups",
                                             arg="TargetGroupArns", key="TargetGroups",
                                             many=True, use_arn=True),
    "lambda:function": dict(svc="lambda", method="get_function_configuration", arg="FunctionName",
                            scalar=True),
    "rds:db": dict(svc="rds", method="describe_db_instances", arg="DBInstanceIdentifier",
                   key="DBInstances", scalar=True),
}


def detail_supported(resource_type: str) -> bool:
    return resource_type in _DETAIL


def _jsonsafe(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")
    if isinstance(obj, dict):
        return {k: _jsonsafe(v) for k, v in obj.items() if k != "ResponseMetadata"}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonsafe(v) for v in obj]
    return obj


def resource_details(session, resource) -> dict:
    """Live, service-specific attributes for one resource: {"detail": {...}} or
    {"detail": None, "note": ...} when unsupported/unavailable. Read-only and graceful."""
    spec = _DETAIL.get(resource.resource_type)
    if not spec:
        return {"detail": None,
                "note": f"no deep-describe mapping for {resource.resource_type} "
                        "(inventory fields only; confirm via the service's describe API)"}
    ident = resource.arn if spec.get("use_arn") else resource.id
    if not ident:
        return {"detail": None, "note": "resource has no id/arn to describe"}
    try:
        api = client(session, spec["svc"], resource.region)
        arg = ident if spec.get("scalar") else [ident]
        resp = getattr(api, spec["method"])(**{spec["arg"]: arg})
        if spec.get("key"):
            items = resp.get(spec["key"], [])
            if spec.get("nested"):
                items = [x for grp in items for x in grp.get(spec["nested"], [])]
            detail = items[0] if items else None
        else:  # scalar API returning the object directly (e.g. get_function_configuration)
            detail = {k: v for k, v in resp.items() if k != "ResponseMetadata"}
        if detail is None:
            return {"detail": None, "note": f"{resource.id} not found via {spec['method']}"}
        return {"detail": _jsonsafe(detail)}
    except Exception as e:
        return {"detail": None, "note": f"{spec['method']}: {type(e).__name__}"}
