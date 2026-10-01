import copy
import tempfile
import unittest
from pathlib import Path

from core import MetricsError, day_of, money
from demo import build_result, fixtures, snapshot
from ledger import Store


class LedgerTests(unittest.TestCase):
    def test_recollection_replaces_without_inflating_totals(self):
        result = build_result()
        self.assertEqual(result["first"], result["repeated"])
        self.assertEqual(result["refreshed"]["records"], 2)
        self.assertEqual(result["refreshed"]["gross"], "200000")
        self.assertEqual(result["refreshed"]["refunds"], "40000")
        self.assertEqual(result["first"]["refunds"], "30000")

    def test_unknown_day_is_held_but_verified_zero_is_kept(self):
        result = build_result()
        self.assertEqual(result["refreshed"]["rows"][2]["gross"], "0")
        self.assertIsNone(result["refreshed"]["rows"][-1]["gross"])
        self.assertEqual(sum(p["action"] == "hold" for p in result["plan"]), 2)

    def test_source_identity_is_isolated_by_account_and_brand(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "test.sqlite")
            try:
                batch = fixtures()[0]
                store.save("first-brand", batch)
                store.save("second-brand", batch)
                other = copy.deepcopy(batch)
                other.account = "second-account"
                store.save("first-brand", other)
                self.assertEqual(store.db.execute("SELECT count(*) FROM records").fetchone()[0], 3)
            finally:
                store.close()

    def test_demo_and_live_modes_cannot_share_database(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "test.sqlite")
            try:
                batch = fixtures()[0]
                store.save("demo-brand", batch)
                batch.mode = "live"
                with self.assertRaises(MetricsError):
                    store.save("demo-brand", batch)
            finally:
                store.close()

    def test_money_and_timezone_contract(self):
        self.assertEqual(money("0.1") + money("0.2"), money("0.3"))
        self.assertEqual(day_of("2026-09-01T16:00:00Z"), "2026-09-02")
        for value in (None, True, "NaN"):
            with self.assertRaises(MetricsError):
                money(value)


if __name__ == "__main__":
    unittest.main()
