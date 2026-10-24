"""Import Octopus Energy Italy gas readings as Home Assistant statistics.

The distributor reports one cumulative meter index (m3) per month, dated the last
day of the month. Consumption is the difference between consecutive readings, so
the statistic keeps the raw index as its state and the consumption since the
first reading as its sum, which is what the Energy dashboard plots.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify
from homeassistant.util.unit_conversion import VolumeConverter

from .const import DOMAIN, GAS_HISTORY_DAYS
from .statistics import build_statistic_metadata


def parse_gas_readings(edges) -> list[dict]:
    """Keep actual readings, as a chronological list of {"date", "index"}."""
    readings = [
        {
            "date": date.fromisoformat(edge["node"]["readingDate"]),
            "index": float(edge["node"]["consumptionValue"]),
        }
        for edge in edges
        if edge["node"]["readingType"] == "ACTUAL"
        and edge["node"]["consumptionValue"] is not None
    ]
    readings.sort(key=lambda reading: reading["date"])
    return readings


def reading_start(reading: dict, timezone: ZoneInfo) -> datetime:
    """The hour that ends the reading's day, so the month's gas lands in that month."""
    return dt_util.as_utc(datetime.combine(reading["date"], time(23), tzinfo=timezone))


def build_gas_statistics(
    readings: list[dict], timezone: ZoneInfo, base: tuple[float, float] | None
) -> list[StatisticData]:
    """Build cumulative statistics continuing from base, a (index, sum) pair."""
    previous_index, total = base if base else (readings[0]["index"], 0.0)
    statistics = []
    for reading in readings:
        # A lower index means the meter was replaced; that month's usage is unknown.
        total += max(reading["index"] - previous_index, 0.0)
        previous_index = reading["index"]
        statistics.append(
            StatisticData(
                start=reading_start(reading, timezone),
                state=reading["index"],
                sum=total,
            )
        )
    return statistics


def get_gas_statistic_id(account_number: str) -> str:
    return f"{DOMAIN}:{slugify(account_number)}_gas_consumption"


async def async_get_last_gas_row(
    hass: HomeAssistant, before: datetime, statistic_id: str
) -> tuple[float, float] | None:
    """Return (index, sum) of the last statistic recorded before `before`."""
    found = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        before - timedelta(days=GAS_HISTORY_DAYS),
        before,
        {statistic_id},
        "hour",
        None,
        {"state", "sum"},
    )
    rows = found.get(statistic_id)
    return (rows[-1]["state"], rows[-1]["sum"]) if rows else None


async def async_import_gas_statistics(
    hass: HomeAssistant,
    account_number: str,
    readings: list[dict],
    timezone: ZoneInfo,
) -> None:
    """Import readings; safe to call repeatedly with overlapping windows."""
    if not readings:
        return

    statistic_id = get_gas_statistic_id(account_number)
    base = await async_get_last_gas_row(
        hass, reading_start(readings[0], timezone), statistic_id
    )
    async_add_external_statistics(
        hass,
        build_statistic_metadata(
            statistic_id,
            "Octopus IT Gas Consumption",
            UnitOfVolume.CUBIC_METERS,
            VolumeConverter.UNIT_CLASS,
        ),
        build_gas_statistics(readings, timezone, base),
    )
