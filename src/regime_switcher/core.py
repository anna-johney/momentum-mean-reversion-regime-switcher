"""Signal generation and close-to-close backtesting, using only the standard library."""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Config:
    regime_window: int = 20
    momentum_window: int = 20
    reversion_window: int = 20
    efficiency_threshold: float = 0.35
    z_threshold: float = 0.5
    cost_bps: float = 5.0
    periods_per_year: int = 252

    def __post_init__(self) -> None:
        for name in ("regime_window", "momentum_window", "reversion_window"):
            if getattr(self, name) < 2:
                raise ValueError(f"{name} must be at least 2")
        if not math.isfinite(self.efficiency_threshold) or not 0 <= self.efficiency_threshold <= 1:
            raise ValueError("efficiency_threshold must be finite and between 0 and 1")
        if self.z_threshold < 0 or not math.isfinite(self.z_threshold):
            raise ValueError("z_threshold must be finite and nonnegative")
        if not 0 <= self.cost_bps < 5000 or not math.isfinite(self.cost_bps):
            raise ValueError("cost_bps must be finite and between 0 and 5000")
        if self.periods_per_year < 1:
            raise ValueError("periods_per_year must be positive")


def load_prices(path: str | Path) -> list[tuple[date, float]]:
    """Read a strictly increasing date,close CSV; reject bad or ambiguous inputs."""
    prices: list[tuple[date, float]] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"date", "close"}.issubset(reader.fieldnames):
            raise ValueError("CSV must contain lowercase date and close columns")
        for line, row in enumerate(reader, start=2):
            try:
                d = date.fromisoformat(row["date"].strip())
                close = float(row["close"])
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"Invalid date or close on CSV line {line}") from exc
            if not math.isfinite(close) or close <= 0:
                raise ValueError(f"Close must be finite and positive on CSV line {line}")
            if prices and d <= prices[-1][0]:
                raise ValueError(f"Dates must be strictly increasing on CSV line {line}")
            prices.append((d, close))
    if not prices:
        raise ValueError("CSV contains no price rows")
    return prices


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def _signals(closes: list[float], i: int, cfg: Config) -> tuple[str, float, int, int, int]:
    changes = [closes[j] - closes[j - 1] for j in range(i - cfg.regime_window + 1, i + 1)]
    path_length = sum(abs(change) for change in changes)
    efficiency = abs(closes[i] - closes[i - cfg.regime_window]) / path_length if path_length else 0.0
    regime = "momentum" if efficiency >= cfg.efficiency_threshold else "mean_reversion"
    momentum = _sign(closes[i] - closes[i - cfg.momentum_window])
    window = closes[i - cfg.reversion_window + 1 : i + 1]
    mean = statistics.fmean(window)
    sigma = statistics.pstdev(window)
    z = (closes[i] - mean) / sigma if sigma else 0.0
    reversion = -_sign(z) if abs(z) >= cfg.z_threshold and sigma else 0
    switched = momentum if regime == "momentum" else reversion
    return regime, efficiency, momentum, reversion, switched


def backtest(prices: list[tuple[date, float]], cfg: Config = Config()) -> list[dict]:
    """A close-t signal fills at close t+1, then earns the t+1-to-t+2 return."""
    warmup = max(cfg.regime_window, cfg.momentum_window, cfg.reversion_window - 1)
    if len(prices) < warmup + 4:
        raise ValueError(f"Need at least {warmup + 4} price rows for this configuration")
    closes = [close for _, close in prices]
    equity = {name: 1.0 for name in ("switcher", "momentum", "mean_reversion")}
    previous = {name: 0 for name in equity}
    rows: list[dict] = []
    for i in range(warmup + 1, len(prices) - 1):
        signal_i = i - 1
        regime, efficiency, momentum, reversion, switched = _signals(closes, signal_i, cfg)
        asset_return = closes[i + 1] / closes[i] - 1.0
        row = {
            "signal_date": prices[signal_i][0].isoformat(),
            "fill_date": prices[i][0].isoformat(),
            "return_date": prices[i + 1][0].isoformat(),
            "signal_close": closes[signal_i],
            "fill_close": closes[i],
            "next_close": closes[i + 1],
            "efficiency_ratio": efficiency,
            "regime": regime,
            "asset_return": asset_return,
        }
        for name, position in (("switcher", switched), ("momentum", momentum), ("mean_reversion", reversion)):
            turnover = abs(position - previous[name])
            cost = turnover * cfg.cost_bps / 10000.0
            net_return = (1.0 - cost) * (1.0 + position * asset_return) - 1.0
            if net_return <= -1:
                raise ValueError(f"{name} loses at least 100% on {prices[i + 1][0]}; short exposure cannot be modeled past bankruptcy")
            equity[name] *= 1.0 + net_return
            row[f"{name}_position"] = position
            row[f"{name}_turnover"] = turnover
            row[f"{name}_return"] = net_return
            row[f"{name}_equity"] = equity[name]
            previous[name] = position
        rows.append(row)
    return rows


def _metrics(rows: list[dict], name: str, periods: int) -> dict:
    returns = [row[f"{name}_return"] for row in rows]
    mean = statistics.fmean(returns)
    volatility = statistics.stdev(returns) if len(returns) > 1 else 0.0
    sharpe = mean / volatility * math.sqrt(periods) if volatility else None
    peak = 1.0
    max_drawdown = 0.0
    for row in rows:
        peak = max(peak, row[f"{name}_equity"])
        max_drawdown = min(max_drawdown, row[f"{name}_equity"] / peak - 1.0)
    return {
        "sharpe": sharpe,
        "total_return": rows[-1][f"{name}_equity"] - 1.0,
        "annualized_return": rows[-1][f"{name}_equity"] ** (periods / len(rows)) - 1.0,
        "annualized_volatility": volatility * math.sqrt(periods),
        "max_drawdown": max_drawdown,
        "total_turnover": sum(row[f"{name}_turnover"] for row in rows),
        "active_days": sum(row[f"{name}_position"] != 0 for row in rows),
    }


def summarize(rows: list[dict], cfg: Config) -> dict:
    if not rows:
        raise ValueError("No backtest rows")
    strategies = {name: _metrics(rows, name, cfg.periods_per_year) for name in ("switcher", "momentum", "mean_reversion")}
    baseline = max((name for name in ("momentum", "mean_reversion") if strategies[name]["sharpe"] is not None), key=lambda name: strategies[name]["sharpe"], default=None)
    switch_sharpe = strategies["switcher"]["sharpe"]
    base_sharpe = strategies[baseline]["sharpe"] if baseline else None
    # Relative Sharpe improvement is meaningful only against a positive baseline.
    improvement = (switch_sharpe / base_sharpe - 1.0) * 100 if switch_sharpe is not None and base_sharpe is not None and base_sharpe > 0 else None
    return {
        "config": asdict(cfg),
        "period": {"first_signal": rows[0]["signal_date"], "last_return": rows[-1]["return_date"], "return_intervals": len(rows)},
        "strategies": strategies,
        "best_static_by_sharpe": baseline,
        "sharpe_improvement_vs_best_static_percent": improvement,
        "regime_days": {"momentum": sum(row["regime"] == "momentum" for row in rows), "mean_reversion": sum(row["regime"] == "mean_reversion" for row in rows)},
        "interpretation": "Hypothetical research backtest; zero risk-free rate; no financing, borrow, spread, tax, or market-impact model.",
    }
