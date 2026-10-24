from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.octopus_it.const import SENSOR_TYPES
from custom_components.octopus_it.statistics import (
    async_import_statistics,
    build_metadata,
    build_statistics,
    get_statistic_id,
    parse_daily_readings,
)

ROME = ZoneInfo("Europe/Rome")
ACCOUNT = "A-1234ABCD"


def edge(start: str, total: float, f1=0.0, f2=0.0, f3=0.0):
    return {
        "node": {
            "value": str(total),
            "startAt": start,
            "metaData": {
                "statistics": [
                    {"label": "F1", "value": str(f1)},
                    {"label": "F2", "value": str(f2)},
                    {"label": "F3", "value": str(f3)},
                ]
            },
        }
    }


def reading(day: int, total: float):
    return {
        "start": datetime(2026, 10, day, tzinfo=ROME),
        "daily_total": total,
        "daily_f1": total / 2,
        "daily_f2": total / 4,
        "daily_f3": total / 4,
    }


def test_parse_daily_readings_sorts_and_splits_bands():
    edges = [
        edge("2026-10-21T00:00:00+02:00", 3.0, 1.0, 1.5, 0.5),
        edge("2026-10-20T00:00:00+02:00", 2.0, 0.5, 0.5, 1.0),
    ]

    readings = parse_daily_readings(edges, ROME)

    assert [r["daily_total"] for r in readings] == [2.0, 3.0]
    assert readings[1]["daily_f1"] == 1.0
    assert readings[1]["daily_f2"] == 1.5
    assert readings[1]["daily_f3"] == 0.5


def test_parse_daily_readings_assumes_rome_for_naive_timestamps():
    readings = parse_daily_readings([edge("2026-10-21T00:00:00", 1.0)], ROME)

    assert readings[0]["start"] == datetime(2026, 10, 21, tzinfo=ROME)


def test_build_statistics_is_cumulative_and_hour_aligned_utc():
    stats = build_statistics([reading(20, 2.0), reading(21, 3.0)], "daily_total", 10.0)

    assert [s["sum"] for s in stats] == [12.0, 15.0]
    # Rome is UTC+2 on these dates, so local midnight is 22:00 UTC the day before.
    assert stats[0]["start"] == datetime(2026, 10, 19, 22, tzinfo=timezone.utc)
    assert stats[1]["start"] == datetime(2026, 10, 20, 22, tzinfo=timezone.utc)


def test_metadata_uses_energy_unit_and_account_scoped_id():
    metadata = build_metadata(ACCOUNT, "daily_f1")

    assert metadata["statistic_id"] == "octopus_it:a_1234abcd_daily_f1"
    assert metadata["unit_of_measurement"] == "kWh"
    assert metadata["has_sum"] is True
    assert metadata["source"] == "octopus_it"


async def _read_sums(hass: HomeAssistant, sensor_key: str) -> dict:
    """Return {start (UTC): sum} for everything recorded for a sensor."""
    statistic_id = get_statistic_id(ACCOUNT, sensor_key)
    await async_wait_recording_done(hass)
    found = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        None,
        {statistic_id},
        "hour",
        None,
        {"sum"},
    )
    return {
        datetime.fromtimestamp(row["start"], timezone.utc): row["sum"]
        for row in found.get(statistic_id, [])
    }


async def test_import_records_each_reading_on_the_day_it_belongs_to(
    recorder_mock, hass: HomeAssistant
):
    await async_import_statistics(
        hass, ACCOUNT, [reading(19, 1.0), reading(20, 2.0), reading(21, 4.0)]
    )

    sums = await _read_sums(hass, "daily_total")

    assert sums == {
        datetime(2026, 10, 18, 22, tzinfo=timezone.utc): 1.0,
        datetime(2026, 10, 19, 22, tzinfo=timezone.utc): 3.0,
        datetime(2026, 10, 20, 22, tzinfo=timezone.utc): 7.0,
    }


async def test_import_creates_a_statistic_per_sensor(
    recorder_mock, hass: HomeAssistant
):
    await async_import_statistics(hass, ACCOUNT, [reading(20, 4.0)])

    assert await _read_sums(hass, "daily_f1") == {
        datetime(2026, 10, 19, 22, tzinfo=timezone.utc): 2.0
    }
    for sensor_key in SENSOR_TYPES:
        assert await _read_sums(hass, sensor_key)


async def test_overlapping_reimport_keeps_sums_consistent(
    recorder_mock, hass: HomeAssistant
):
    await async_import_statistics(
        hass, ACCOUNT, [reading(19, 1.0), reading(20, 2.0), reading(21, 4.0)]
    )
    # Next poll: window slides forward, day 21 is revised and day 22 appears.
    await async_import_statistics(
        hass, ACCOUNT, [reading(20, 2.0), reading(21, 5.0), reading(22, 8.0)]
    )

    sums = await _read_sums(hass, "daily_total")

    assert [sums[k] for k in sorted(sums)] == [1.0, 3.0, 8.0, 16.0]


async def test_import_with_no_readings_is_a_noop(recorder_mock, hass: HomeAssistant):
    await async_import_statistics(hass, ACCOUNT, [])

    assert await _read_sums(hass, "daily_total") == {}
