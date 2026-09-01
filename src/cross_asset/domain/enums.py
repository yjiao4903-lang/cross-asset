from enum import StrEnum


class AssetClass(StrEnum):
    CN_EQ = "CN_EQ"
    HK_EQ = "HK_EQ"
    US_EQ = "US_EQ"
    CN_BOND = "CN_BOND"
    GOLD = "GOLD"
    COMMODITY = "COMMODITY"
    CASH = "CASH"


class DataQuality(StrEnum):
    OK = "ok"
    STALE = "stale"
    MISSING = "missing"
    FAILED = "failed"
    CLOSED = "closed"
    FALLBACK = "fallback"


class Frequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    IRREGULAR = "irregular"


class PointInTimeClass(StrEnum):
    MARKET_CLOSE = "market_close"
    RELEASED = "released"
    MANUAL = "manual"


class ProviderName(StrEnum):
    FRED = "fred"
    YAHOO = "yahoo"
    TUSHARE = "tushare"
    WIND = "wind"
    IFIND = "ifind"
    MANUAL = "manual"
