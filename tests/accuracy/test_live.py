"""Live accuracy reconciliation against real Cost Explorer. Opt-in (costs a few CE requests):
    FINOPS_ACCURACY_LIVE=1 pytest tests/accuracy/test_live.py
"""
import os

import pytest


@pytest.mark.skipif(not os.getenv("FINOPS_ACCURACY_LIVE"),
                    reason="set FINOPS_ACCURACY_LIVE=1 to run the live Cost Explorer check")
def test_live_reconcile():
    from finops_core.accuracy import reconcile
    r = reconcile(period="3m")
    assert r["ok"], r
