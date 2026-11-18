import csv
import math
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from regime_switcher import Config, backtest, load_prices, summarize


def series(values):
    start = date(2024, 1, 1)
    return [(start + timedelta(days=i), float(value)) for i, value in enumerate(values)]


class BacktestTests(unittest.TestCase):
    def test_signals_use_only_current_and_earlier_prices(self):
        cfg = Config(2, 2, 2, 0.5, 0.5, 0)
        base = backtest(series([100, 101, 102, 103, 104, 105]), cfg)
        changed = backtest(series([100, 101, 102, 103, 104, 200]), cfg)
        self.assertEqual(len(base), 2)
        for key in ("regime", "efficiency_ratio", "switcher_position", "momentum_position", "mean_reversion_position"):
            self.assertEqual(base[-1][key], changed[-1][key])
        self.assertNotEqual(base[-1]["switcher_return"], changed[-1]["switcher_return"])

    def test_trend_switches_to_momentum_and_cost_is_charged(self):
        cfg = Config(2, 2, 2, 0.5, 0.5, 10)
        rows = backtest(series([100, 101, 102, 103, 104, 105]), cfg)
        first = rows[0]
        self.assertEqual(first["regime"], "momentum")
        self.assertEqual(first["switcher_position"], 1)
        self.assertEqual(first["mean_reversion_position"], -1)
        self.assertEqual(first["switcher_turnover"], 1)
        self.assertEqual(first["signal_date"], date(2024, 1, 3).isoformat())
        self.assertEqual(first["fill_date"], date(2024, 1, 4).isoformat())
        expected = (1 - 0.001) * (104 / 103) - 1
        self.assertAlmostEqual(first["switcher_return"], expected)
        self.assertEqual(rows[1]["switcher_turnover"], 0)

    def test_choppy_market_selects_reversion(self):
        rows = backtest(series([100, 105, 100, 105, 100, 105]), Config(2, 2, 2, 0.5, 0.5, 0))
        self.assertEqual(rows[0]["regime"], "mean_reversion")
        self.assertEqual(rows[0]["switcher_position"], rows[0]["mean_reversion_position"])
        self.assertEqual(rows[0]["switcher_position"], 1)

    def test_all_strategies_share_dates_and_report(self):
        cfg = Config(2, 2, 2, 0.5, 0.5, 0)
        rows = backtest(series([100, 101, 102, 100, 103, 99, 104]), cfg)
        report = summarize(rows, cfg)
        self.assertEqual(report["period"]["return_intervals"], len(rows))
        self.assertEqual(set(report["strategies"]), {"switcher", "momentum", "mean_reversion"})
        self.assertEqual(sum(report["regime_days"].values()), len(rows))
        for name in report["strategies"]:
            self.assertAlmostEqual(math.prod(1 + r[f"{name}_return"] for r in rows), rows[-1][f"{name}_equity"])

    def test_invalid_prices_and_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            Config(efficiency_threshold=float("nan"))
        with self.assertRaises(ValueError):
            backtest(series([100, 101]), Config())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerows([("date", "close"), ("2024-01-02", "100"), ("2024-01-02", "101")])
            with self.assertRaisesRegex(ValueError, "strictly increasing"):
                load_prices(path)


if __name__ == "__main__":
    unittest.main()
