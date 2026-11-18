# Momentum vs. Mean-Reversion Regime Switcher

A reproducible research backtest for one daily price series. The project turns the image's idea into an explicit, testable rule. The image's “18% Sharpe improvement” is a claim to evaluate, **not** a result this project assumes.

## Quick start

Requires Python 3.10 or later. Run from this project folder. No installation, third-party packages, or network access are needed.

```bash
PYTHONPATH=src python3 -m regime_switcher demo --out-dir results/demo
PYTHONPATH=src python3 -m regime_switcher backtest --input data/prices.csv --out-dir results/real
python3 -m unittest discover -s tests -v
```

`demo` creates **synthetic** prices for a plumbing check; its results cannot validate any performance claim. For a real backtest, supply `data/prices.csv` with an ISO date and a positive close on each row, sorted oldest to newest:

```csv
date,close
2024-01-02,100.00
2024-01-03,100.45
```

Supply substantially more than 20 rows; a useful evaluation needs a long history with different market conditions. Use an appropriately adjusted, verified series when corporate actions apply. The input may be any one liquid asset, but the model assumes it can be shorted.

## Fixed rules

At each close, the **efficiency ratio** is the absolute price change over the last 20 intervals divided by the sum of absolute changes across those intervals. A value at least 0.35 selects momentum; a lower value selects mean reversion. This indicator uses only prices known at that close.

- Momentum position: +1 if today's close exceeds the close 20 observations earlier, -1 if below, otherwise 0.
- Mean-reversion position: compare today's close with the 20-close rolling mean; take the opposite sign when the absolute population z-score is at least 0.5, otherwise 0.
- Switcher position: the selected strategy's position. The two static comparators apply their respective signals every day.
- A signal formed at close *t* is filled at close *t+1* and held over the close *t+1* to close *t+2* interval. Each change in position incurs 5 basis points per unit of turnover, including the initial entry and short-to-long reversals. Signal date, fill date, position, turnover, net return, and equity for every interval are in `daily.csv`.

The three strategies share the same warm-up and evaluation dates. `summary.json` reports annualized Sharpe using 252 periods and a zero risk-free rate, total/annualized return, volatility, drawdown, turnover, and regime counts. The Sharpe improvement is `(switcher Sharpe / best static Sharpe - 1) × 100`; it is left undefined if the best static Sharpe is nonpositive or any required Sharpe is undefined. All parameters can be changed via `--help`, but comparing many settings on the same history can overfit it.

## Limits and honest interpretation

This is a hypothetical close-to-close research model, not an execution system. Its next-close fill is an approximation: real close auction execution and costs can differ. It includes a simple per-turnover cost but no spread variation, slippage, financing, borrow availability or fees, dividends beyond what the input price incorporates, taxes, or market impact. Short positions can lose more than the initial capital; the run stops if a period would exhaust equity. There is no parameter fitting, out-of-sample selection, walk-forward validation, or live trading connection. Treat any observed 18% improvement as dataset- and assumption-specific until it survives those checks.
