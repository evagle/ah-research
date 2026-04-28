"""Integration layer — one concrete client per upstream data source, all
exposed through small, focused Protocols so the DataRepository can DI them
freely and tests can substitute fakes without touching real networks.

Public surface: the Protocols. Concrete clients (baostock, akshare) are
imported from their own subpackages at the call site.
"""

from ah_research.integrations._protocols import (
    CalendarSource,
    ConstituentsSource,
    CorporateActionsSource,
    FundamentalsSource,
    FXSource,
    PriceSource,
    SectorSource,
)

__all__ = [
    "CalendarSource",
    "ConstituentsSource",
    "CorporateActionsSource",
    "FXSource",
    "FundamentalsSource",
    "PriceSource",
    "SectorSource",
]
