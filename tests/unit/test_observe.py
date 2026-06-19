from finops_core.observe import ApiMeter


def test_meter_counts_and_estimates_ce_cost():
    m = ApiMeter()
    m.record("ce", "GetCostAndUsage")
    m.record("ce", "GetCostForecast")
    m.record("budgets", "DescribeBudgets")
    s = m.summary()
    assert s["api_calls"] == 3
    assert s["ce_requests"] == 2
    assert s["estimated_ce_cost_usd"] == 0.02


def test_handler_reads_operation_model():
    m = ApiMeter()

    class SM:
        service_name = "ce"

    class Model:
        name = "GetCostAndUsage"
        service_model = SM()

    m._handler(model=Model())
    m._handler(model=None)  # tolerated
    assert m.summary()["ce_requests"] == 1


def test_instrument_registers_after_call():
    class BotoCore:
        def __init__(self):
            self.events = []

        def register(self, event, handler):
            self.events.append(event)

    class Session:
        def __init__(self):
            self._session = BotoCore()

    s = Session()
    ApiMeter().instrument(s)
    assert "after-call" in s._session.events
