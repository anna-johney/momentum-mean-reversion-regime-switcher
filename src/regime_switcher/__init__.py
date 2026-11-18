"""Transparent, single-asset regime-switching backtest."""

from .core import Config, backtest, load_prices, summarize

__all__ = ["Config", "backtest", "load_prices", "summarize"]
