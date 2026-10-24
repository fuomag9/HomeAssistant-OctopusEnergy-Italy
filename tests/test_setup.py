from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.octopus_it.const import DOMAIN

from .test_gas import node, read_gas_sums
from .test_statistics import ACCOUNT, _read_sums, edge


def api_response(payload: dict) -> dict:
    operation = payload["operationName"]
    if operation == "Login":
        return {
            "data": {
                "obtainKrakenToken": {
                    "token": "token",
                    "refreshToken": "refresh",
                    "refreshExpiresIn": 1,
                }
            }
        }
    if operation == "GetAccountList":
        return {"data": {"viewer": {"accounts": [{"number": ACCOUNT}]}}}
    if operation == "GetAccountProperties":
        return {"data": {"account": {"properties": [{"id": "property"}]}}}
    if operation == "GetMetersForProperty":
        return {
            "data": {
                "property": {
                    "electricitySupplyPoints": [
                        {"id": "1", "pod": "IT001E00000000", "isSmartMeter": True}
                    ]
                }
            }
        }
    if operation == "GetGasSupplyPoints":
        return {
            "data": {
                "property": {
                    "gasSupplyPoints": [{"pdr": "12345678901234", "isSmartMeter": True}]
                }
            }
        }
    if operation == "GetGasReadings":
        return {
            "data": {
                "gasMeterReadings": {
                    "edges": [node("2026-08-31", 100), node("2026-09-30", 108)]
                }
            }
        }
    assert operation == "GetSmartUsage", operation
    return {
        "data": {
            "property": {
                "measurements": {
                    "edges": [
                        edge("2026-10-20T00:00:00+02:00", 2.0, 1.0, 0.5, 0.5),
                        edge("2026-10-21T00:00:00+02:00", 3.0, 1.0, 1.5, 0.5),
                    ]
                }
            }
        }
    }


def fake_session():
    def post(url, json=None, headers=None):
        resp = MagicMock(status=200)
        resp.json = AsyncMock(return_value=api_response(json))
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=resp)
        context.__aexit__ = AsyncMock(return_value=False)
        return context

    session = MagicMock(post=post)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


async def test_config_entry_sets_up_sensors_and_statistics(
    recorder_mock, enable_custom_integrations, hass: HomeAssistant
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"},
        options={CONF_SCAN_INTERVAL: 3600},
    )
    entry.add_to_hass(hass)

    with patch("aiohttp.ClientSession", side_effect=lambda *a, **k: fake_session()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)

    total = hass.states.get("sensor.octopus_it_daily_total")
    assert total.state == "3.0"
    assert total.attributes["measurement_date"] == "2026-10-21"
    assert "state_class" not in total.attributes
    assert hass.states.get("sensor.octopus_it_daily_f2").state == "1.5"

    sums = await _read_sums(hass, "daily_total")
    assert [sums[start] for start in sorted(sums)] == [2.0, 5.0]
    assert await read_gas_sums(hass) == [0.0, 8.0]


async def test_a_gas_failure_does_not_affect_the_electricity_sensors(
    recorder_mock, enable_custom_integrations, hass: HomeAssistant, caplog
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"},
        options={CONF_SCAN_INTERVAL: 3600},
    )
    entry.add_to_hass(hass)

    with (
        patch("aiohttp.ClientSession", side_effect=lambda *a, **k: fake_session()),
        patch(
            "custom_components.octopus_it.OctopusCoordinator.async_import_gas_statistics",
            side_effect=Exception("gas is down"),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get("sensor.octopus_it_daily_total").state == "3.0"
    assert "Could not import gas readings" in caplog.text
