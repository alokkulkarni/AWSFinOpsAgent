import xml.etree.ElementTree as ET

from devops_core.diagram.topology_drawio import build_topology_drawio
from devops_core.schemas.topology import Instance, Peering, Subnet, Topology, Vpc

TOPO = Topology(
    region="eu-west-2",
    vpcs=[
        Vpc(id="vpc-1", cidr="10.0.0.0/16", name="main", igw="igw-1",
            subnets=[Subnet(id="subnet-a", cidr="10.0.1.0/24", az="eu-west-2a", vpc="vpc-1",
                            public=True, instances=[Instance(id="i-1", type="t3.micro", subnet="subnet-a")])]),
        Vpc(id="vpc-2", cidr="10.1.0.0/16", name="data"),
    ],
    peerings=[Peering(id="pcx-1", requester_vpc="vpc-1", accepter_vpc="vpc-2", status="active")],
)


def test_topology_drawio_well_formed_nested_with_edges():
    xml = build_topology_drawio(TOPO)
    root = ET.fromstring(xml)
    assert root.tag == "mxGraphModel"
    ids = [c.get("id") for c in root.iter("mxCell")]
    assert "0" in ids and "1" in ids and len(ids) == len(set(ids))
    assert "<!--" not in xml
    assert "vpc-1" in xml and "subnet-a" in xml and "i-1" in xml
    assert "mxgraph.aws4" in xml

    edges = [c for c in root.iter("mxCell") if c.get("edge") == "1"]
    assert len(edges) >= 1                                 # the peering edge
    for e in edges:
        assert e.find("mxGeometry") is not None            # every edge has geometry
