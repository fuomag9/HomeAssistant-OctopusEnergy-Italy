from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.octopus_it import OctopusCoordinator
from custom_components.octopus_it.gas import (
    async_import_gas_statistics,
    build_gas_statistics,
    get_gas_statistic_id,
    parse_gas_readings,
)

from .test_statistics import ACCOUNT

ROME = ZoneInfo("Europe/Rome")
STATISTIC_ID = get_gas_statistic_id(ACCOUNT)


def node(day: str, index: int, kind: str = "ACTUAL"):
    return {
        "node": {
            "readingDate": day,
            "readingType": kind,
            "consumptionValue": f"{index}.000000000000000",
        }
    }


def reading(day: str, index: float):
    return {"date": date.fromisoformat(day), "index": float(index)}


JAN, FEB, MAR, APR, MAY = (
    reading("2026-01-31", 100),
    reading("2026-02-28", 112),
    reading("2026-03-31", 130),
    reading("2026-04-30", 141),
    reading("2026-05-31", 150),
)


def test_parse_keeps_only_actual_readings_in_date_order():
    edges = [
        node("2026-03-31", 130),
        node("2026-02-28", 112),
        node("2026-02-15", 106, kind="ESTIMATE"),
        node("2026-01-31", 100, kind="CUSTOMER_SELF_READING"),
    ]

    assert parse_gas_readings(edges) == [FEB, MAR]


def test_first_reading_is_the_baseline_and_sums_are_differences():
    stats = build_gas_statistics([JAN, FEB, MAR], ROME, None)

    assert [s["sum"] for s in stats] == [0.0, 12.0, 30.0]
    assert [s["state"] for s in stats] == [100.0, 112.0, 130.0]
    # 23:00 Rome time on the reading day (UTC+1 in winter), so it falls in that month.
    assert stats[0]["start"] == datetime(2026, 1, 31, 22, tzinfo=timezone.utc)


def test_sums_continue_from_the_last_stored_row():
    stats = build_gas_statistics([FEB, MAR], ROME, (112.0, 12.0))

    assert [s["sum"] for s in stats] == [12.0, 30.0]


def test_a_lower_index_after_a_meter_replacement_adds_nothing():
    stats = build_gas_statistics(
        [JAN, FEB, reading("2026-03-31", 5), reading("2026-04-30", 9)], ROME, None
    )

    assert [s["sum"] for s in stats] == [0.0, 12.0, 12.0, 16.0]


async def monthly_changes(hass: HomeAssistant) -> list[float]:
    """The per-month consumption, as the Energy dashboard queries it."""
    await async_wait_recording_done(hass)
    found = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        None,
        {STATISTIC_ID},
        "month",
        None,
        {"change"},
    )
    return [row["change"] for row in found.get(STATISTIC_ID, [])]


async def read_gas_sums(hass: HomeAssistant) -> list[float]:
    await async_wait_recording_done(hass)
    found = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        None,
        {STATISTIC_ID},
        "hour",
        None,
        {"sum"},
    )
    return [row["sum"] for row in found.get(STATISTIC_ID, [])]


async def test_import_gives_each_month_its_own_consumption(
    recorder_mock, hass: HomeAssistant
):
    await hass.config.async_set_time_zone("Europe/Rome")

    await async_import_gas_statistics(hass, ACCOUNT, [JAN, FEB, MAR, APR], ROME)

    assert (await monthly_changes(hass))[-3:] == [12.0, 18.0, 11.0]


async def test_import_continues_after_the_window_slides_and_a_reading_arrives(
    recorder_mock, hass: HomeAssistant
):
    await hass.config.async_set_time_zone("Europe/Rome")
    await async_import_gas_statistics(hass, ACCOUNT, [JAN, FEB, MAR, APR], ROME)

    # A month later: January has dropped out of the window and May has arrived.
    await async_import_gas_statistics(hass, ACCOUNT, [FEB, MAR, APR, MAY], ROME)

    assert (await monthly_changes(hass))[-4:] == [12.0, 18.0, 11.0, 9.0]
    assert await read_gas_sums(hass) == [0.0, 12.0, 30.0, 41.0, 50.0]


async def test_import_with_no_readings_is_a_noop(recorder_mock, hass: HomeAssistant):
    await async_import_gas_statistics(hass, ACCOUNT, [], ROME)

    assert await read_gas_sums(hass) == []


def fake_session(responses: dict, calls: list):
    def post(url, json=None, headers=None):
        calls.append(json)
        resp = MagicMock(status=200)
        resp.json = AsyncMock(return_value={"data": responses[json["operationName"]]})
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=resp)
        context.__aexit__ = AsyncMock(return_value=False)
        return context

    session = MagicMock(post=post)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def make_coordinator(hass: HomeAssistant) -> OctopusCoordinator:
    coordinator = OctopusCoordinator(hass, "user@example.com", "secret", 3600)
    coordinator._token = "token"
    coordinator._token_expires_at = float("inf")
    coordinator._account_number = ACCOUNT
    coordinator._property_id = "property"
    return coordinator


async def test_coordinator_imports_gas_readings_for_the_gas_supply_point(
    recorder_mock, hass: HomeAssistant, freezer
):
    freezer.move_to("2026-10-24 12:00:00+00:00")
    calls = []
    responses = {
        "GetGasSupplyPoints": {
            "property": {
                "gasSupplyPoints": [
                    {"pdr": "00000000000001", "isSmartMeter": False},
                    {"pdr": "00000000000002", "isSmartMeter": True},
                ]
            }
        },
        "GetGasReadings": {
            "gasMeterReadings": {
                "edges": [node("2026-01-31", 100), node("2026-02-28", 112)]
            }
        },
    }

    with patch("aiohttp.ClientSession", return_value=fake_session(responses, calls)):
        await make_coordinator(hass).async_import_gas_statistics()

    variables = calls[-1]["variables"]
    assert variables["accountNumber"] == ACCOUNT
    assert variables["pdr"] == "00000000000002"  # the smart meter is preferred
    assert variables["dateTo"] == "2026-10-24"
    assert variables["dateFrom"] == "2024-10-24"  # 730 days earlier
    assert await read_gas_sums(hass) == [0.0, 12.0]


async def test_coordinator_does_nothing_without_a_gas_supply_point(
    recorder_mock, hass: HomeAssistant
):
    calls = []
    responses = {"GetGasSupplyPoints": {"property": {"gasSupplyPoints": []}}}

    with patch("aiohttp.ClientSession", return_value=fake_session(responses, calls)):
        await make_coordinator(hass).async_import_gas_statistics()

    assert [call["operationName"] for call in calls] == ["GetGasSupplyPoints"]
    assert await read_gas_sums(hass) == []
