#!/usr/bin/env python3
"""Run btc_cvd.py, validate its contract, and atomically stage Pages output."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

WINDOWS = ("15m", "1h", "4h", "24h")
EXCHANGES = ("binance", "coinbase", "okx", "bybit")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate(payload: dict, now: datetime | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")
    generated = parse_utc(payload["generated_at"])
    now = now or datetime.now(timezone.utc)
    if generated > now + timedelta(minutes=5):
        raise ValueError("generated_at is unexpectedly in the future")
    if generated < now - timedelta(hours=2):
        raise ValueError("generated_at is already stale")
    windows = payload.get("windows")
    if not isinstance(windows, dict) or set(windows) != set(WINDOWS):
        raise ValueError("windows must be exactly 15m, 1h, 4h and 24h")
    for label in WINDOWS:
        window = windows[label]
        included = window.get("included_exchanges")
        excluded = window.get("excluded_exchanges")
        if not isinstance(included, list) or not isinstance(excluded, list):
            raise ValueError(f"{label}: exchange lists missing")
        if not included:
            raise ValueError(f"{label}: no exchange has complete coverage")
        if set(included) | set(excluded) != set(EXCHANGES) or set(included) & set(excluded):
            raise ValueError(f"{label}: included/excluded exchange partition is invalid")
        if window.get("data_quality") not in {"GOOD", "PARTIAL", "POOR"}:
            raise ValueError(f"{label}: invalid data_quality")
        aggregate = window.get("aggregate", {})
        for field in ("delta_btc", "cvd_btc", "volume_btc"):
            if not isinstance(aggregate.get(field), (int, float)):
                raise ValueError(f"{label}: aggregate.{field} is missing or non-numeric")
        exchanges = window.get("exchanges", {})
        if set(exchanges) != set(EXCHANGES):
            raise ValueError(f"{label}: exchange details are incomplete")
        for exchange in EXCHANGES:
            details = exchanges[exchange]
            if details.get("method") is None or "price_change_pct" not in details:
                raise ValueError(f"{label}/{exchange}: methodology or price change missing")
            if details.get("included_in_aggregate") != (exchange in included):
                raise ValueError(f"{label}/{exchange}: inclusion flags disagree")
    payload["stale_after"] = (generated + timedelta(hours=25)).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload["schema_version"] = 1
    return payload


def generate(script: Path, max_seconds: int) -> dict:
    command = [sys.executable, str(script), "--json", "--max-seconds", str(max_seconds)]
    print(f"Running {' '.join(command)}", file=sys.stderr)
    result = subprocess.run(command, text=True, capture_output=True, timeout=max_seconds + 45)
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode:
        raise RuntimeError(f"btc_cvd.py exited with status {result.returncode}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"btc_cvd.py did not produce valid JSON: {exc}") from exc


def atomic_write(payload: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle, temporary = tempfile.mkstemp(prefix=".btc_cvd.", suffix=".json", dir=destination.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        json.loads(Path(temporary).read_text(encoding="utf-8"))
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path, default=Path(__file__).with_name("btc_cvd.py"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("public") / "btc_cvd.json")
    parser.add_argument("--max-seconds", type=int, default=45)
    args = parser.parse_args()
    payload = validate(generate(args.script, args.max_seconds))
    atomic_write(payload, args.output)
    print(f"Validated and staged {args.output} ({args.output.stat().st_size} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
