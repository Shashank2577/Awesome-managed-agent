"""Telemetry tools for Observe agents — real VictoriaMetrics and Loki queries."""
from __future__ import annotations

import os
import time
from typing import Any

import httpx


async def run_promql(query: str, start: int | None = None, end: int | None = None, step: str = "60s") -> dict[str, Any]:
    """Execute a PromQL query against VictoriaMetrics."""
    base_url = os.getenv("VICTORIAMETRICS_URL", "http://localhost:8428")
    token = os.getenv("OBSERVE_TOKEN")
    params: dict[str, str] = {"query": query}

    if start:
        url = f"{base_url}/api/v1/query_range"
        params["start"] = str(start)
        params["end"] = str(end or int(time.time()))
        params["step"] = step
    else:
        url = f"{base_url}/api/v1/query"

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "success":
        return {"error": f"VictoriaMetrics error: {data}"}

    series = []
    for r in data["data"]["result"]:
        item = {"labels": r.get("metric", {})}
        if "values" in r:
            item["values"] = [[v[0], float(v[1])] for v in r["values"]]
        else:
            item["values"] = [[r["value"][0], float(r["value"][1])]]
        series.append(item)

    return {"resultType": data["data"]["resultType"], "series": series}


async def run_logql(query: str, start: int, end: int, limit: int = 200) -> dict[str, Any]:
    """Execute a LogQL query against Loki."""
    base_url = os.getenv("LOKI_URL", "http://localhost:3100")
    token = os.getenv("OBSERVE_TOKEN")

    params = {
        "query": query,
        "start": str(start * 1_000_000_000),  # Loki expects nanoseconds
        "end": str(end * 1_000_000_000),
        "limit": str(limit),
        "direction": "backward",
    }

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{base_url}/api/v1/query_range", params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "success":
        return {"error": f"Loki error: {data}"}

    streams = []
    for r in data["data"]["result"]:
        streams.append({
            "labels": r.get("stream", {}),
            "entries": [{"ts": int(v[0]) / 1_000_000_000, "line": v[1]} for v in r["values"]],
        })

    return {"streams": streams}


async def list_resources(label_name: str = "namespace") -> list[str]:
    """List available values for a given Prometheus label."""
    base_url = os.getenv("VICTORIAMETRICS_URL", "http://localhost:8428")
    token = os.getenv("OBSERVE_TOKEN")

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{base_url}/api/v1/label/{label_name}/values", headers=headers)
        resp.raise_for_status()
        data = resp.json()

    return data.get("data", [])
