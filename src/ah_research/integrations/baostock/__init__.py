"""Baostock integration — A-shares only (SH/SZ).

Baostock is a free A-share data service; no credentials needed. Login is
still required before any query, and one login covers the entire session.
"""

from ah_research.integrations.baostock.client import BaostockClient

__all__ = ["BaostockClient"]
