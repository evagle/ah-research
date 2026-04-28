"""AKShare integration — HK equities and FX (CNY/HKD).

AKShare is a community-maintained free data aggregator. No credentials
needed. Functions we use:

- ``stock_hk_hist``         — HK daily prices
- ``currency_boc_sina``     — Bank of China FX rates (中间价 / reference rate)
"""

from ah_research.integrations.akshare.client import AKShareClient

__all__ = ["AKShareClient"]
