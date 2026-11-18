"""Command-line interface and explicitly synthetic demonstration data."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from .core import Config, backtest, load_prices, summarize


def make_demo(path: Path, seed: int = 2026) -> None:
    """Write a repeatable toy series with trend and oscillating sections."""
    rng = random.Random(seed)
    day = date(2020, 1, 1)
    close = 100.0
    rows = []
    for i in range(900):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        phase = (i // 150) % 3
        if phase == 0:
            log_return = 0.0012 + rng.gauss(0, 0.006)
        elif phase == 1:
            log_return = -0.0010 + rng.gauss(0, 0.006)
        else:
            log_return = 0.045 * (math.log(100.0) - math.log(close)) + rng.gauss(0, 0.006)
        close *= math.exp(log_return)
        rows.append((day.isoformat(), f"{close:.6f}"))
        day += timedelta(days=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("date", "close"))
        writer.writerows(rows)


def _write_outputs(prices_path: Path, out_dir: Path, cfg: Config, synthetic: bool) -> None:
    rows = backtest(load_prices(prices_path), cfg)
    report = summarize(rows, cfg)
    report["source_file"] = str(prices_path.resolve())
    report["data_origin"] = "generated_synthetic_demo" if synthetic else "user_supplied_unverified"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "daily.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote {out_dir / 'daily.csv'} and {out_dir / 'summary.json'}")
    print(f"Evaluation: {report['period']['first_signal']} to {report['period']['last_return']} ({len(rows)} returns)")
    for name, metrics in report["strategies"].items():
        sharpe = "undefined" if metrics["sharpe"] is None else f"{metrics['sharpe']:.3f}"
        print(f"{name:16} Sharpe {sharpe:>9} | total return {metrics['total_return']:>8.2%} | max drawdown {metrics['max_drawdown']:>8.2%}")
    improvement = report["sharpe_improvement_vs_best_static_percent"]
    print("Sharpe improvement vs best static:", "undefined" if improvement is None else f"{improvement:.2f}%")
    if synthetic:
        print("DEMO USES SYNTHETIC DATA. Its metrics are not evidence of trading performance.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Momentum versus mean-reversion regime backtest")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("backtest", help="Backtest a date,close CSV")
    run.add_argument("--input", required=True, type=Path)
    demo = sub.add_parser("demo", help="Generate synthetic prices and backtest them")
    for command in (run, demo):
        command.add_argument("--out-dir", type=Path, default=Path("results"))
        command.add_argument("--regime-window", type=int, default=20)
        command.add_argument("--momentum-window", type=int, default=20)
        command.add_argument("--reversion-window", type=int, default=20)
        command.add_argument("--efficiency-threshold", type=float, default=0.35)
        command.add_argument("--z-threshold", type=float, default=0.5)
        command.add_argument("--cost-bps", type=float, default=5.0)
    demo.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)
    try:
        cfg = Config(args.regime_window, args.momentum_window, args.reversion_window, args.efficiency_threshold, args.z_threshold, args.cost_bps)
        if args.command == "demo":
            path = args.out_dir / "synthetic_prices.csv"
            make_demo(path, args.seed)
            _write_outputs(path, args.out_dir, cfg, synthetic=True)
        else:
            _write_outputs(args.input, args.out_dir, cfg, synthetic=False)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
