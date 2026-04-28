"""Tests for atrium.core._input_utils.extract_query."""

from __future__ import annotations

import pytest

from atrium.core._input_utils import extract_query


def test_direct_query_key():
    """Explicit 'query' key is returned as-is."""
    assert extract_query({"query": "hello"}) == "hello"


def test_upstream_result_fallback():
    """Falls back to upstream agent result when no direct query."""
    input_data = {"upstream": {"agent_a": {"result": "upstream result"}}}
    assert extract_query(input_data) == "upstream result"


def test_upstream_query_fallback():
    """Falls back to upstream 'query' value when present."""
    input_data = {"upstream": {"agent_a": {"query": "upstream query"}}}
    assert extract_query(input_data) == "upstream query"


def test_upstream_stringified_fallback():
    """Falls back to str(v)[:100] when upstream has no query/result keys."""
    inner = {"some_key": "some_value"}
    input_data = {"upstream": {"agent_a": inner}}
    result = extract_query(input_data)
    assert result == str(inner)[:100]


def test_empty_dict_fallback():
    """Empty dict falls back to str(input_data)[:200], which is '{}'."""
    result = extract_query({})
    # str({}) == '{}' which is 2 chars — non-empty string
    assert result == str({})[:200]


def test_nonempty_dict_no_query_no_upstream():
    """Dict without 'query' or 'upstream' falls back to str(input_data)[:200]."""
    input_data = {"foo": "bar"}
    result = extract_query(input_data)
    assert result == str(input_data)[:200]


def test_query_takes_precedence_over_upstream():
    """Direct 'query' key wins over any upstream data."""
    input_data = {
        "query": "direct",
        "upstream": {"agent_a": {"query": "should be ignored"}},
    }
    assert extract_query(input_data) == "direct"


def test_upstream_non_dict_value_skipped():
    """Upstream values that are not dicts are skipped."""
    input_data = {"upstream": {"agent_a": "plain string"}}
    # No dict value found — falls back to str(input_data)[:200]
    result = extract_query(input_data)
    assert result == str(input_data)[:200]


def test_upstream_none_does_not_crash():
    """upstream=None should not raise AttributeError."""
    result = extract_query({"upstream": None})
    assert isinstance(result, str)
