from finops_core.pricing import estimate_cost, usage_summary


def test_estimate_sonnet_input_output():
    # 1000 in * 0.003/1k + 500 out * 0.015/1k = 0.003 + 0.0075 = 0.0105
    assert estimate_cost("us.anthropic.claude-sonnet-4-5-20250929-v1:0", 1000, 500) == 0.0105


def test_nova_cheaper_than_sonnet():
    nova = estimate_cost("us.amazon.nova-pro-v1:0", 1000, 1000)
    sonnet = estimate_cost("us.anthropic.claude-sonnet-4-5-20250929-v1:0", 1000, 1000)
    assert 0 < nova < sonnet


def test_cache_read_is_cheaper_than_input():
    base = estimate_cost("us.anthropic.claude-sonnet-4-5", input_tokens=1000)
    cached = estimate_cost("us.anthropic.claude-sonnet-4-5", cache_read_tokens=1000)
    assert 0 < cached < base


def test_usage_summary_reads_bedrock_keys():
    s = usage_summary("us.anthropic.claude-sonnet-4-5", {
        "inputTokens": 1000, "outputTokens": 500, "cacheReadInputTokens": 200})
    assert s["input_tokens"] == 1000 and s["output_tokens"] == 500
    assert s["cache_read_tokens"] == 200
    assert s["estimated_usd"] > 0
