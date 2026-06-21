"""Network topology: VPC → subnet → instance nesting + peering/IGW/NAT/endpoints."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Instance:
    id: str
    type: Optional[str] = None
    state: Optional[str] = None
    subnet: Optional[str] = None
    sgs: list = field(default_factory=list)
    name: Optional[str] = None


@dataclass
class Subnet:
    id: str
    cidr: Optional[str] = None
    az: Optional[str] = None
    vpc: Optional[str] = None
    public: bool = False
    name: Optional[str] = None
    instances: list = field(default_factory=list)   # list[Instance]


@dataclass
class Vpc:
    id: str
    cidr: Optional[str] = None
    name: Optional[str] = None
    igw: Optional[str] = None
    nats: list = field(default_factory=list)
    endpoints: list = field(default_factory=list)
    subnets: list = field(default_factory=list)      # list[Subnet]


@dataclass
class Peering:
    id: str
    requester_vpc: str
    accepter_vpc: str
    status: str = ""


@dataclass
class Topology:
    region: str
    vpcs: list = field(default_factory=list)          # list[Vpc]
    peerings: list = field(default_factory=list)       # list[Peering]
    notes: list = field(default_factory=list)

    @property
    def subnet_count(self) -> int:
        return sum(len(v.subnets) for v in self.vpcs)

    @property
    def instance_count(self) -> int:
        return sum(len(s.instances) for v in self.vpcs for s in v.subnets)

    def to_dict(self) -> dict:
        return {
            "region": self.region,
            "vpcs": [asdict(v) for v in self.vpcs],
            "peerings": [asdict(p) for p in self.peerings],
            "counts": {"vpcs": len(self.vpcs), "subnets": self.subnet_count,
                       "instances": self.instance_count, "peerings": len(self.peerings)},
            "notes": self.notes,
        }
