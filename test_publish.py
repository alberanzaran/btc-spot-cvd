import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from publish import EXCHANGES, WINDOWS, atomic_write, validate


def valid_payload():
    exchange = {
        "method": "INDIVIDUAL_TRADES",
        "price_change_pct": 0.1,
        "included_in_aggregate": False,
    }
    windows = {}
    for label in WINDOWS:
        details = {name: copy.deepcopy(exchange) for name in EXCHANGES}
        details["binance"]["included_in_aggregate"] = True
        details["binance"]["method"] = "KLINE_TAKER_PROXY"
        windows[label] = {
            "data_quality": "POOR",
            "included_exchanges": ["binance"],
            "excluded_exchanges": ["coinbase", "okx", "bybit"],
            "aggregate": {"delta_btc": 1.0, "cvd_btc": 1.0, "volume_btc": 2.0},
            "exchanges": details,
        }
    return {"generated_at": "2026-09-07T06:00:00Z", "windows": windows}


class PublishTests(unittest.TestCase):
    def test_contract_and_stale_after(self):
        now = datetime(2026, 9, 7, 6, 1, tzinfo=timezone.utc)
        payload = validate(valid_payload(), now=now)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["stale_after"], "2026-09-08T07:00:00Z")

    def test_rejects_inconsistent_inclusion(self):
        payload = valid_payload()
        payload["windows"]["15m"]["exchanges"]["okx"]["included_in_aggregate"] = True
        with self.assertRaisesRegex(ValueError, "inclusion flags disagree"):
            validate(payload, now=datetime(2026, 9, 7, 6, 1, tzinfo=timezone.utc))

    def test_rejects_window_without_usable_source(self):
        payload = valid_payload()
        window = payload["windows"]["24h"]
        window["included_exchanges"] = []
        window["excluded_exchanges"] = list(EXCHANGES)
        window["exchanges"]["binance"]["included_in_aggregate"] = False
        with self.assertRaisesRegex(ValueError, "no exchange has complete coverage"):
            validate(payload, now=datetime(2026, 9, 7, 6, 1, tzinfo=timezone.utc))

    def test_atomic_output_is_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "btc_cvd.json"
            atomic_write({"generated_at": "now"}, target)
            self.assertEqual(json.loads(target.read_text()), {"generated_at": "now"})


if __name__ == "__main__":
    unittest.main()
