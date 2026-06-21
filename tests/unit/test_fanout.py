from devops_core.discovery import engine as eng
from devops_core.discovery.engine import EstateScanner
from devops_core.schemas.estate import Resource


def _bare_scanner(monkeypatch):
    sc = EstateScanner.__new__(EstateScanner)
    sc.cfg = type("C", (), {"aws": type("A", (), {"region": "us-east-1"})()})()
    sc.session = "mgmt"
    monkeypatch.setattr(sc, "enabled_regions", lambda: ["us-east-1"])
    return sc


def test_fan_out_aggregates_members_and_notes_failures(monkeypatch):
    sc = _bare_scanner(monkeypatch)

    def fake_scan_one(session, regions, source):
        if session == "mgmt":
            return ([Resource.from_arn("arn:aws:ec2:us-east-1:111:instance/i-mgmt")], [], ["tagging"])
        if session == "member-222":
            return ([Resource.from_arn("arn:aws:ec2:eu-west-2:222:instance/i-dev")], [], ["tagging"])
        return ([], [], [])

    monkeypatch.setattr(sc, "_scan_one", fake_scan_one)
    monkeypatch.setattr(eng, "_caller_account", lambda session: "111")

    class FakeOrg:
        def __init__(self, *a, **k):
            pass

        def list_accounts(self):
            return {"accounts": [{"id": "111", "name": "mgmt"}, {"id": "222", "name": "dev"},
                                 {"id": "333", "name": "locked"}]}

        def assume_account(self, acct, role_name):
            if acct == "222":
                return "member-222"
            raise RuntimeError("AccessDenied")

    monkeypatch.setattr(eng, "OrgResolver", FakeOrg)

    est = sc.scan(regions=["us-east-1"], fan_out=True, role_name="X")
    ids = {r.id for r in est.resources}
    assert "i-mgmt" in ids and "i-dev" in ids                 # mgmt + member 222 scanned
    assert {r.account for r in est.resources} >= {"111", "222"}
    assert any("333" in n for n in est.notes)                 # locked account skipped + noted
    assert est.accounts == ["111", "222"]
