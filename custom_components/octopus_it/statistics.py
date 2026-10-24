"""Import Octopus Energy Italy daily readings as Home Assistant statistics.

Octopus publishes smart meter data with a delay (currently about two days). A
sensor can only report a value "now", so Home Assistant would record that value
against the day it was polled instead of the day it was consumed. Writing the
readings as external statistics lets us stamp them with the day they belong to.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify
from homeassistant.util.unit_conversion import EnergyConverter

try:
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:  # Home Assistant < 2025.10
    StatisticMeanType = None

from .const import DOMAIN, SENSOR_TYPES, HISTORY_DAYS


def parse_daily_readings(edges, timezone: ZoneInfo) -> list[dict]:
    """Convert GraphQL measurement edges into a chronological list of daily readings."""
    readings = []
    for edge in edges:
        node = edge["node"]
        start = dt_util.parse_datetime(node["startAt"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone)

        f_values = {"F1": 0.0, "F2": 0.0, "F3": 0.0}
        for entry in node.get("metaData", {}).get("statistics", []):
            label = entry.get("label")
            if label in f_values:
                f_values[label] = float(entry.get("value", 0.0))

        readings.append(
            {
                "start": start,
                "daily_total": float(node.get("value", 0.0)),
                "daily_f1": f_values["F1"],
                "daily_f2": f_values["F2"],
                "daily_f3": f_values["F3"],
            }
        )

    readings.sort(key=lambda reading: reading["start"])
    return readings


def build_statistics(readings, sensor_key: str, base_sum: float) -> list[StatisticData]:
    """Build cumulative statistics, one row per day, continuing from base_sum."""
    statistics = []
    total = base_sum
    for reading in readings:
        total += reading[sensor_key]
        statistics.append(
            StatisticData(
                start=dt_util.as_utc(reading["start"]).replace(
                    minute=0, second=0, microsecond=0
                ),
                state=total,
                sum=total,
            )
        )
    return statistics


def get_statistic_id(account_number: str, sensor_key: str) -> str:
    return f"{DOMAIN}:{slugify(account_number)}_{sensor_key}"


def build_metadata(account_number: str, sensor_key: str) -> StatisticMetaData:
    metadata = StatisticMetaData(
        has_sum=True,
        name=f"Octopus IT {SENSOR_TYPES[sensor_key][0]}",
        source=DOMAIN,
        statistic_id=get_statistic_id(account_number, sensor_key),
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    if StatisticMeanType is None:
        metadata["has_mean"] = False
    else:
        metadata["mean_type"] = StatisticMeanType.NONE
        metadata["unit_class"] = EnergyConverter.UNIT_CLASS
    return metadata


async def async_get_last_sum(
    hass: HomeAssistant, before: datetime, statistic_id: str
) -> float:
    """Return the cumulative sum of the last statistic recorded before `before`."""
    found = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        before - timedelta(days=HISTORY_DAYS * 2),
        before,
        {statistic_id},
        "hour",
        None,
        {"sum"},
    )
    rows = found.get(statistic_id)
    return rows[-1]["sum"] if rows else 0.0


async def async_import_statistics(
    hass: HomeAssistant, account_number: str, readings: list[dict]
) -> None:
    """Import readings; safe to call repeatedly with overlapping windows."""
    if not readings:
        return

    first_start = dt_util.as_utc(readings[0]["start"])
    for sensor_key in SENSOR_TYPES:
        metadata = build_metadata(account_number, sensor_key)
        base_sum = await async_get_last_sum(
            hass, first_start, metadata["statistic_id"]
        )
        async_add_external_statistics(
            hass, metadata, build_statistics(readings, sensor_key, base_sum)
        )
