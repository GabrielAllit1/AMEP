from enum import Enum


class NavMode(str, Enum):
    NOMINAL = "NOMINAL"
    GPS_DENIED_RESILIENT = "GPS_DENIED_RESILIENT"
    DEGRADED_DEAD_RECKONING = "DEGRADED_DEAD_RECKONING"
    SAFE_HOLD = "SAFE_HOLD"


class SensorHealth(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    ISOLATED = "ISOLATED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class AuthoritySource(str, Enum):
    OPERATOR = "OPERATOR"
    AUTONOMY = "AUTONOMY"
    SAFETY = "SAFETY"
