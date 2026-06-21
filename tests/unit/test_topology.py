import boto3
from botocore.stub import Stubber

from devops_core.discovery import topology as topo


def test_topology_nests_vpc_subnet_instance(monkeypatch):
    c = boto3.client("ec2", region_name="eu-west-2",
                     aws_access_key_id="x", aws_secret_access_key="y", aws_session_token="z")
    stub = Stubber(c)
    stub.add_response("describe_vpcs", {"Vpcs": [
        {"VpcId": "vpc-1", "CidrBlock": "10.0.0.0/16", "Tags": [{"Key": "Name", "Value": "main"}]}]})
    stub.add_response("describe_subnets", {"Subnets": [
        {"SubnetId": "subnet-a", "CidrBlock": "10.0.1.0/24", "AvailabilityZone": "eu-west-2a",
         "VpcId": "vpc-1", "MapPublicIpOnLaunch": True}]})
    stub.add_response("describe_instances", {"Reservations": [{"Instances": [
        {"InstanceId": "i-1", "InstanceType": "t3.micro", "State": {"Name": "running"},
         "SubnetId": "subnet-a", "SecurityGroups": [{"GroupId": "sg-1"}]}]}]})
    stub.add_response("describe_internet_gateways", {"InternetGateways": [
        {"InternetGatewayId": "igw-1", "Attachments": [{"VpcId": "vpc-1"}]}]})
    stub.add_response("describe_nat_gateways", {"NatGateways": []})
    stub.add_response("describe_vpc_endpoints", {"VpcEndpoints": []})
    stub.add_response("describe_vpc_peering_connections", {"VpcPeeringConnections": []})
    stub.activate()
    monkeypatch.setattr(topo, "client", lambda session, service, region=None: c)

    t = topo.TopologyScanner().scan("eu-west-2")
    assert len(t.vpcs) == 1
    v = t.vpcs[0]
    assert v.id == "vpc-1" and v.name == "main" and v.igw == "igw-1"
    assert len(v.subnets) == 1
    sub = v.subnets[0]
    assert sub.id == "subnet-a" and sub.public is True and sub.az == "eu-west-2a"
    assert len(sub.instances) == 1 and sub.instances[0].id == "i-1"
    assert t.instance_count == 1 and t.subnet_count == 1
