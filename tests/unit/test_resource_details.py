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


class _FakeIam:
    def get_role(self, RoleName):
        return {"Role": {"RoleName": RoleName, "Arn": f"arn:aws:iam::1:role/{RoleName}"}}


def test_wrap_shape_unwraps_single_key(monkeypatch):
    import devops_core.discovery.details as mod
    monkeypatch.setattr(mod, "client", lambda session, svc, region=None: _FakeIam())
    role = Resource.from_arn("arn:aws:iam::1:role/my-role")
    out = resource_details(object(), role)
    assert out["detail"]["RoleName"] == "my-role"


class _FakeEcs:
    def describe_services(self, cluster, services):
        return {"services": [{"serviceName": services[0], "cluster": cluster, "status": "ACTIVE"}]}


def test_ecs_service_parses_cluster_from_id(monkeypatch):
    import devops_core.discovery.details as mod
    monkeypatch.setattr(mod, "client", lambda session, svc, region=None: _FakeEcs())
    # ARN arn:aws:ecs:r:a:service/cluster-name/svc-name → id "cluster-name/svc-name"
    svc = Resource.from_arn("arn:aws:ecs:eu-west-2:1:service/prod-cluster/web")
    out = resource_details(object(), svc)
    assert out["detail"]["cluster"] == "prod-cluster"
    assert out["detail"]["serviceName"] == "web"


def test_normalized_type_key_for_elb_listener(monkeypatch):
    # Resource Explorer emits 'elasticloadbalancing:listener/app' → normalizes to :listener
    import devops_core.discovery.details as mod

    class _Elb:
        def describe_listeners(self, ListenerArns):
            return {"Listeners": [{"ListenerArn": ListenerArns[0], "Port": 443}]}
    monkeypatch.setattr(mod, "client", lambda session, svc, region=None: _Elb())
    r = Resource.from_arn("arn:aws:elasticloadbalancing:eu-west-2:1:listener/app/lb/abc/def")
    r.resource_type = "elasticloadbalancing:listener/app"  # RE-native form
    out = resource_details(object(), r)
    assert out["detail"]["Port"] == 443


def test_unsupported_type_is_graceful():
    r = Resource.from_arn("arn:aws:wisdom:eu-west-2:1:assistant/xyz")
    out = resource_details(object(), r)
    assert out["detail"] is None and out.get("note")


def test_detail_supported_flags_common_services():
    for rt in ("ec2:network-interface", "iam:role", "s3", "sqs", "dynamodb:table",
               "cloudfront:distribution", "elasticloadbalancing:listener/app"):
        assert detail_supported(rt), rt
    assert not detail_supported("wisdom:assistant")
