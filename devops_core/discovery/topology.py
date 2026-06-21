"""Network topology discovery via EC2 describes — VPC → subnet → instance + IGW/NAT/endpoints
+ peering. Graceful: each describe is wrapped, failures become notes. (Single-page describes;
pagination is a hardening item.)
"""
from __future__ import annotations

from typing import Optional

from finops_core.aws.session import build_session, client
from finops_core.config import Config
from devops_core.schemas.topology import Instance, Peering, Subnet, Topology, Vpc


def _name(tags) -> Optional[str]:
    for t in tags or []:
        if t.get("Key") == "Name":
            return t.get("Value")
    return None


class TopologyScanner:
    def __init__(self, session=None, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self.session = session

    def scan(self, region: str) -> Topology:
        if self.session is None:
            self.session = build_session(self.cfg)
        ec2 = client(self.session, "ec2", region)
        notes: list = []
        vpcs: dict = {}
        subnets: dict = {}

        try:
            for v in ec2.describe_vpcs().get("Vpcs", []):
                vpcs[v["VpcId"]] = Vpc(id=v["VpcId"], cidr=v.get("CidrBlock"), name=_name(v.get("Tags")))
        except Exception as e:
            notes.append(f"vpcs: {type(e).__name__}")

        try:
            for s in ec2.describe_subnets().get("Subnets", []):
                sub = Subnet(id=s["SubnetId"], cidr=s.get("CidrBlock"), az=s.get("AvailabilityZone"),
                             vpc=s.get("VpcId"), public=s.get("MapPublicIpOnLaunch", False),
                             name=_name(s.get("Tags")))
                subnets[sub.id] = sub
                if sub.vpc in vpcs:
                    vpcs[sub.vpc].subnets.append(sub)
        except Exception as e:
            notes.append(f"subnets: {type(e).__name__}")

        try:
            for res in ec2.describe_instances().get("Reservations", []):
                for inst in res.get("Instances", []):
                    i = Instance(id=inst["InstanceId"], type=inst.get("InstanceType"),
                                 state=inst.get("State", {}).get("Name"), subnet=inst.get("SubnetId"),
                                 sgs=[g["GroupId"] for g in inst.get("SecurityGroups", [])],
                                 name=_name(inst.get("Tags")))
                    if i.subnet in subnets:
                        subnets[i.subnet].instances.append(i)
        except Exception as e:
            notes.append(f"instances: {type(e).__name__}")

        try:
            for igw in ec2.describe_internet_gateways().get("InternetGateways", []):
                for att in igw.get("Attachments", []):
                    if att.get("VpcId") in vpcs:
                        vpcs[att["VpcId"]].igw = igw["InternetGatewayId"]
        except Exception as e:
            notes.append(f"igw: {type(e).__name__}")

        try:
            for nat in ec2.describe_nat_gateways().get("NatGateways", []):
                if nat.get("VpcId") in vpcs:
                    vpcs[nat["VpcId"]].nats.append(nat["NatGatewayId"])
        except Exception as e:
            notes.append(f"nat: {type(e).__name__}")

        try:
            for ep in ec2.describe_vpc_endpoints().get("VpcEndpoints", []):
                if ep.get("VpcId") in vpcs:
                    vpcs[ep["VpcId"]].endpoints.append(ep.get("ServiceName", "").rsplit(".", 1)[-1])
        except Exception as e:
            notes.append(f"endpoints: {type(e).__name__}")

        peerings: list = []
        try:
            for p in ec2.describe_vpc_peering_connections().get("VpcPeeringConnections", []):
                peerings.append(Peering(
                    id=p["VpcPeeringConnectionId"],
                    requester_vpc=p.get("RequesterVpcInfo", {}).get("VpcId", ""),
                    accepter_vpc=p.get("AccepterVpcInfo", {}).get("VpcId", ""),
                    status=p.get("Status", {}).get("Code", "")))
        except Exception as e:
            notes.append(f"peering: {type(e).__name__}")

        return Topology(region=region, vpcs=list(vpcs.values()), peerings=peerings, notes=notes)
