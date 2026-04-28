"""Phase 3 acceptance tests for the claude_code_stream_json translator.

Driven by tests/fixtures/oas_stream_sample.jsonl — a recorded OAS transcript.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atrium.harness.bridge import (
    AtriumEventDraft,
    translate_claude_code,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "oas_stream_sample.jsonl"


def load_fixture() -> list[dict]:
    events = []
    for line in FIXTURE_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


# ---------------------------------------------------------------------------
# Individual event type tests
# ---------------------------------------------------------------------------

def test_translator_handles_init_message():
    event = {"type": "system", "subtype": "init", "model": "anthropic:claude-sonnet-4-6"}
    drafts = translate_claude_code(event)
    # system/init is dropped — not user-facing
    assert drafts == []


def test_translator_emits_harness_thinking_for_thinking_blocks():
    event = {
        "type": "assistant",
        "message": {
            "content": [{"type": "thinking", "thinking": "Let me think..."}],
        },
    }
    drafts = translate_claude_code(event)
    assert any(d.type == "HARNESS_THINKING" for d in drafts)
    thinking = next(d for d in drafts if d.type == "HARNESS_THINKING")
    assert thinking.payload["text"] == "Let me think..."


def test_translator_emits_harness_message_for_text_blocks():
    event = {
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": "Here is the answer."}],
        },
    }
    drafts = translate_claude_code(event)
    assert any(d.type == "HARNESS_MESSAGE" for d in drafts)
    msg = next(d for d in drafts if d.type == "HARNESS_MESSAGE")
    assert msg.payload["text"] == "Here is the answer."


def test_translator_emits_harness_tool_called_for_tool_use_blocks():
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "ls"}}
            ],
        },
    }
    drafts = translate_claude_code(event)
    assert any(d.type == "HARNESS_TOOL_CALLED" for d in drafts)
    tc = next(d for d in drafts if d.type == "HARNESS_TOOL_CALLED")
    assert tc.payload["tool"] == "bash"
    assert tc.payload["input"] == {"command": "ls"}


def test_translator_emits_harness_tool_result_for_tool_result_blocks():
    event = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "file1.py\nfile2.py",
                }
            ],
        },
    }
    drafts = translate_claude_code(event)
    assert any(d.type == "HARNESS_TOOL_RESULT" for d in drafts)
    tr = next(d for d in drafts if d.type == "HARNESS_TOOL_RESULT")
    assert "file1.py" in tr.payload["output"]


def test_translator_emits_budget_consumed_with_real_token_counts():
    event = {
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": "Done."}],
            "usage": {"input_tokens": 512, "output_tokens": 100},
        },
        "_model": "anthropic:claude-sonnet-4-6",
    }
    drafts = translate_claude_code(event)
    assert any(d.type == "BUDGET_CONSUMED" for d in drafts)
    bc = next(d for d in drafts if d.type == "BUDGET_CONSUMED")
    assert bc.payload["tokens_in"] == 512
    assert bc.payload["tokens_out"] == 100
    assert "cost_usd" in bc.payload


def test_translator_returns_terminal_for_result_event():
    event = {"type": "result", "subtype": "success", "result": "All done."}
    drafts = translate_claude_code(event)
    # result → HARNESS_MESSAGE
    assert any(d.type == "HARNESS_MESSAGE" for d in drafts)
    msg = next(d for d in drafts if d.type == "HARNESS_MESSAGE")
    assert msg.payload["text"] == "All done."


def test_translator_drops_unknown_event_types_gracefully():
    event = {"type": "some_future_event", "data": "ignored"}
    drafts = translate_claude_code(event)
    assert drafts == []


def test_assistant_message_with_multiple_blocks_emits_one_event_per_block_in_order():
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "thinking", "thinking": "planning..."},
                {"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "pwd"}},
                {"type": "text", "text": "Running command."},
            ],
        },
    }
    drafts = translate_claude_code(event)
    types = [d.type for d in drafts]
    assert types[0] == "HARNESS_THINKING"
    assert types[1] == "HARNESS_TOOL_CALLED"
    assert types[2] == "HARNESS_MESSAGE"


# ---------------------------------------------------------------------------
# Fixture-driven tests — drive every event in the recorded transcript
# ---------------------------------------------------------------------------

def test_fixture_file_exists():
    assert FIXTURE_PATH.exists(), f"Fixture not found: {FIXTURE_PATH}"


def test_full_fixture_produces_expected_event_sequence():
    events = load_fixture()
    all_drafts: list[AtriumEventDraft] = []
    for event in events:
        all_drafts.extend(translate_claude_code(event))

    types = [d.type for d in all_drafts]
    assert "HARNESS_THINKING" in types
    assert "HARNESS_TOOL_CALLED" in types
    assert "HARNESS_TOOL_RESULT" in types
    assert "HARNESS_MESSAGE" in types
    assert "BUDGET_CONSUMED" in types
    # system init is dropped
    assert "SYSTEM_INIT" not in types


def test_fixture_thinking_text_matches():
    events = load_fixture()
    thinking_events = []
    for event in events:
        for draft in translate_claude_code(event):
            if draft.type == "HARNESS_THINKING":
                thinking_events.append(draft)
    assert len(thinking_events) >= 1
    assert "listing" in thinking_events[0].payload["text"].lower()


def test_fixture_tool_call_is_bash():
    events = load_fixture()
    tool_calls = []
    for event in events:
        for draft in translate_claude_code(event):
            if draft.type == "HARNESS_TOOL_CALLED":
                tool_calls.append(draft)
    assert len(tool_calls) >= 2
    assert tool_calls[0].payload["tool"] == "bash"


def test_fixture_total_input_tokens():
    events = load_fixture()
    total_in = 0
    for event in events:
        for draft in translate_claude_code(event):
            if draft.type == "BUDGET_CONSUMED":
                total_in += draft.payload["tokens_in"]
    # Fixture has multiple usage events — sum must be > 0
    assert total_in > 0
