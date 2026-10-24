from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.octopus_it import OctopusCoordinator

from .test_statistics import ACCOUNT, _read_sums, edge


def fake_session(response: dict):
    """Build a stand-in for aiohttp.ClientSession whose post() returns `response`."""
    resp = MagicMock(status=200)
    resp.json = AsyncMock(return_value=response)
    post = MagicMock()
    post.return_value.__aenter__ = AsyncMock(return_value=resp)
    post.return_value.__aexit__ = AsyncMock(return_value=False)
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
    coordinator._market_supply_point_id = "IT001E00000000"
    return coordinator


def measurements(*edges):
    return {"data": {"property": {"measurements": {"edges": list(edges)}}}}


async def test_update_reports_latest_complete_day_and_imports_history(
    recorder_mock, hass: HomeAssistant, freezer
):
    freezer.move_to("2026-10-24 12:00:00+00:00")
    session = fake_session(
        measurements(
            edge("2026-10-20T00:00:00+02:00", 2.0, 1.0, 0.5, 0.5),
            edge("2026-10-21T00:00:00+02:00", 3.0, 1.0, 1.5, 0.5),
        )
    )

    with patch("aiohttp.ClientSession", return_value=session):
        data = await make_coordinator(hass)._async_update_data()

    # Octopus only has data up to a couple of days ago; the sensors must say which day.
    assert data["measurement_date"] == "2026-10-21"
    assert data["daily_total"] == 3.0
    assert data["daily_f2"] == 1.5

    sums = await _read_sums(hass, "daily_total")
    assert [sums[start] for start in sorted(sums)] == [2.0, 5.0]


@pytest.mark.parametrize(
    ("now", "expected_start", "expected_end"),
    [
        # Rome is UTC+2: local midnight is 22:00 UTC the previous day.
        ("2026-10-24 12:00:00+00:00", "2026-09-23T22:00:00Z", "2026-10-23T22:00:00Z"),
        # Window crosses the end of DST (UTC+2 -> UTC+1) but stays on local midnights.
        ("2026-11-05 12:00:00+00:00", "2026-10-05T22:00:00Z", "2026-11-04T23:00:00Z"),
    ],
)
async def test_request_window_is_aligned_to_rome_midnight(
    recorder_mock, hass: HomeAssistant, freezer, now, expected_start, expected_end
):
    freezer.move_to(now)
    session = fake_session(measurements())

    with patch("aiohttp.ClientSession", return_value=session):
        await make_coordinator(hass)._async_update_data()

    variables = session.post.call_args.kwargs["json"]["variables"]
    assert variables["timezone"] == "Europe/Rome"
    assert variables["startAt"] == expected_start
    assert variables["endAt"] == expected_end


async def test_update_without_readings_returns_zeroes_and_no_date(
    recorder_mock, hass: HomeAssistant
):
    session = fake_session(measurements())

    with patch("aiohttp.ClientSession", return_value=session):
        data = await make_coordinator(hass)._async_update_data()

    assert data["daily_total"] == 0.0
    assert data["measurement_date"] is None
