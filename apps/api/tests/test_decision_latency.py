from quantnifty.decision_latency import stage_timer, summarize_latency


def test_stage_timer_and_summary_are_deterministic_shape():
    stages = {}
    with stage_timer(stages, "analytics"):
        sum(range(10))
    result = summarize_latency(stages)
    assert result["unit"] == "ms"
    assert result["critical_path"] is True
    assert result["stages"]["analytics"] >= 0
    assert result["total_ms"] >= result["stages"]["analytics"]
