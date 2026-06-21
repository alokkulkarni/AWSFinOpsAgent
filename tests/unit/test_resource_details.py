"""On-demand deep describe: resource_details fetches the live, service-specific attributes the
thin inventory omits (e.g. an ENI's Status / Attachment / Description) so the agent can give a
*confirmed* answer instead of "likely". Uses a fake client — no AWS."""
from datetime import datetime

from devops_core.discovery.details import detail_supported, resource_details
from devops_core.schemas.estate import Resource


class _FakeEC2:
    def describe_network_interfaces(self, NetworkInterfaceIds):
        assert NetworkInterfaceIds == ["eni-1"]
        return {"NetworkInterfaces": [{
            "NetworkInterfaceId": "eni-1", "Status": "in-use",
            "Description": "ELB app/my-alb/abc",
            "Attachment": {"InstanceId": None, "AttachTime": datetime(2026, 6, 1, 12, 0)},
        }]}

    def describe_instances(self, InstanceIds):
        return {"Reservations": [{"Instances": [{"InstanceId": InstanceIds[0], "State": {"Name": "running"}}]}]}


def test_eni_detail_exposes_status_and_attachment(monkeypatch):
    import devops_core.discovery.details as mod
    monkeypatch.setattr(mod, "client", lambda session, svc, region=None: _FakeEC2())
    eni = Resource.from_arn("arn:aws:ec2:eu-west-2:1:network-interface/eni-1")
    out = resource_details(object(), eni)
    assert out["detail"]["Status"] == "in-use"
    assert out["detail"]["Description"].startswith("ELB")
    # datetime made JSON-safe (string), not a raw datetime
    assert isinstance(out["detail"]["Attachment"]["AttachTime"], str)


def test_instance_detail_unwraps_reservations(monkeypatch):
    import devops_core.discovery.details as mod
    monkeypatch.setattr(mod, "client", lambda session, svc, region=None: _FakeEC2())
    inst = Resource.from_arn("arn:aws:ec2:eu-west-2:1:instance/i-9")
    out = resource_details(object(), inst)
    assert out["detail"]["InstanceId"] == "i-9"
    assert out["detail"]["State"]["Name"] == "running"


def test_unsupported_type_is_graceful():
    r = Resource.from_arn("arn:aws:sns:eu-west-2:1:my-topic")
    out = resource_details(object(), r)
    assert out["detail"] is None and out.get("note")


def test_detail_supported_flags_eni():
    assert detail_supported("ec2:network-interface")
    assert not detail_supported("sns:")
