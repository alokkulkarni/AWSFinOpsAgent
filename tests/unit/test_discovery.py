import boto3
from botocore.stub import Stubber

from devops_core.discovery import resource_explorer, tagging


def _client(service, region="eu-west-2"):
    return boto3.client(service, region_name=region,
                        aws_access_key_id="x", aws_secret_access_key="y", aws_session_token="z")


def test_resource_explorer_normalizes(monkeypatch):
    c = _client("resource-explorer-2")
    stub = Stubber(c)
    stub.add_response("search", {"Resources": [{
        "Arn": "arn:aws:ec2:eu-west-2:1:subnet/subnet-abc", "Service": "ec2",
        "ResourceType": "ec2:subnet", "Region": "eu-west-2", "OwningAccountId": "1",
        "Properties": [{"Name": "tags", "Data": [{"Key": "Name", "Value": "web"}]}]}]})
    stub.activate()
    monkeypatch.setattr(resource_explorer, "client", lambda session, service, region=None: c)

    rs = resource_explorer.search(None, "eu-west-2")
    assert len(rs) == 1
    r = rs[0]
    assert r.service == "ec2" and r.resource_type == "ec2:subnet"
    assert r.region == "eu-west-2" and r.account == "1" and r.tags["Name"] == "web"


def test_tagging_normalizes(monkeypatch):
    c = _client("resourcegroupstaggingapi")
    stub = Stubber(c)
    stub.add_response("get_resources", {"ResourceTagMappingList": [{
        "ResourceARN": "arn:aws:lambda:eu-west-2:1:function:fn",
        "Tags": [{"Key": "env", "Value": "prod"}]}]})
    stub.activate()
    monkeypatch.setattr(tagging, "client", lambda session, service, region=None: c)

    rs = tagging.get_resources(None, "eu-west-2")
    assert rs[0].service == "lambda" and rs[0].id == "fn" and rs[0].tags["env"] == "prod"
