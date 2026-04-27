import json
from atrium.core.models import AtriumEvent
from atrium.streaming.bus import format_sse, format_sse_end


def test_format_sse():
    event = AtriumEvent(
        event_id="e1", thread_id="t1", type="AGENT_RUNNING",
        payload={"agent_key": "alpha"}, sequence=1,
    )
    result = format_sse(event)
    assert result.startswith("event: AGENT_RUNNING\n")
    assert "data: " in result
    assert result.endswith("\n\n")
    data_line = [l for l in result.split("\n") if l.startswith("data: ")][0]
    parsed = json.loads(data_line[6:])
    assert parsed["type"] == "AGENT_RUNNING"
    assert parsed["sequence"] == 1


def test_format_sse_end():
    result = format_sse_end()
    assert result == "event: end\ndata: {}\n\n"
