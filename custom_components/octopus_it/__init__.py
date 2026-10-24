import base64
import json
import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    API_BASE,
    LOGIN_QUERY,
    GET_PROPERTIES_QUERY,
    GET_METERS_QUERY,
    GET_SMART_USAGE_QUERY,
    GET_GAS_SUPPLY_POINTS_QUERY,
    GET_GAS_READINGS_QUERY,
    DEFAULT_SCAN_INTERVAL,
    GAS_HISTORY_DAYS,
    GAS_SCAN_INTERVAL,
    HISTORY_DAYS,
    SENSOR_TYPES, GET_ACCOUNT_LIST_QUERY,
    TIMEZONE,
)
from .gas import async_import_gas_statistics, parse_gas_readings
from .statistics import async_import_statistics, parse_daily_readings

_LOGGER = logging.getLogger(__name__)

TOKEN_EXPIRY_MARGIN = 60  # seconds before `exp` at which we stop using a token
FALLBACK_TOKEN_LIFETIME = 30 * 60  # seconds, used if the token can't be decoded


def token_expires_at(token: str) -> float:
    """Return the time (unix seconds) at which a JWT should no longer be used."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return float(claims["exp"]) - TOKEN_EXPIRY_MARGIN
    except (IndexError, KeyError, TypeError, ValueError):
        return time.time() + FALLBACK_TOKEN_LIFETIME


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Octopus Italy from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = OctopusCoordinator(hass, email, password, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    async def import_gas(_now=None):
        # Gas is optional, so a failure here must never affect the electricity sensors.
        try:
            await coordinator.async_import_gas_statistics()
        except Exception:
            _LOGGER.warning("Could not import gas readings", exc_info=True)

    entry.async_create_background_task(hass, import_gas(), "octopus_it_gas_import")
    entry.async_on_unload(
        async_track_time_interval(
            hass, import_gas, timedelta(seconds=GAS_SCAN_INTERVAL)
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class OctopusCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from Octopus Energy Italy."""

    def __init__(self, hass, email, password, scan_interval):
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._email = email
        self._password = password
        self._token = None
        self._token_expires_at = 0.0
        self._account_number = None
        self._property_id = None
        self._market_supply_point_id = None
        self._timezone = None
        self._gas_pdr = None

    async def _async_get_timezone(self):
        if self._timezone is None:
            self._timezone = await self.hass.async_add_executor_job(
                dt_util.get_time_zone, TIMEZONE
            )
        return self._timezone

    async def _async_get_token(self):
        """Obtain or refresh JWT token."""
        import aiohttp

        if self._token and time.time() < self._token_expires_at:
            return self._token

        payload = {
            "operationName": "Login",
            "variables": {"input": {"email": self._email, "password": self._password}},
            "query": LOGIN_QUERY,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(API_BASE, json=payload) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Failed to log in: HTTP {resp.status}")
                data = await resp.json()
        try:
            token_data = data["data"]["obtainKrakenToken"]
            self._token = token_data["token"]
            self._token_expires_at = token_expires_at(self._token)
            self._account_number = await self._get_account_list()
            return self._token
        except Exception as e:
            raise UpdateFailed(f"Error parsing token response: {e}")

    async def _get_account_list(self, ):
        import aiohttp
        headers = {
            "Authorization": self._token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "operationName": "GetAccountList",
            "variables": {},
            "query": GET_ACCOUNT_LIST_QUERY,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(API_BASE, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    raise Exception(f"GraphQL query failed with HTTP {resp.status}")
                iddy = await resp.json()
                # Todo: do not hardcode to first house only
        return iddy['data']['viewer']['accounts'][0]['number']
    async def _async_get_property_id(self):
        """Fetch the user’s property ID (if not already known)."""
        if self._property_id:
            return self._property_id

        token = await self._async_get_token()
        if not self._account_number:
            raise UpdateFailed("Cannot determine account number from token.")

        headers = {"Authorization": token}
        payload = {
            "operationName": "GetAccountProperties",
            "variables": {"accountNumber": self._account_number},
            "query": GET_PROPERTIES_QUERY,
        }

        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(API_BASE, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Failed to get properties: HTTP {resp.status}")
                data = await resp.json()

        try:
            props = data["data"]["account"]["properties"]
            if not props:
                raise UpdateFailed("No properties found in account.")
            self._property_id = props[0]["id"]
            return self._property_id
        except Exception as e:
            raise UpdateFailed(f"Error parsing properties: {e}")

    async def _async_get_market_supply_point(self):
        """Fetch the electricitySupplyPoints to find the POD (marketSupplyPointId)."""
        if self._market_supply_point_id:
            return self._market_supply_point_id

        token = await self._async_get_token()
        property_id = await self._async_get_property_id()
        headers = {"Authorization": token}
        payload = {
            "operationName": "GetMetersForProperty",
            "variables": {"propertyId": property_id},
            "query": GET_METERS_QUERY,
        }

        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(API_BASE, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Failed to get meters: HTTP {resp.status}")
                data = await resp.json()

        try:
            meters = data["data"]["property"]["electricitySupplyPoints"]
            for m in meters:
                if m.get("isSmartMeter"):
                    self._market_supply_point_id = m.get("pod")
                    break
            if not self._market_supply_point_id and meters:
                self._market_supply_point_id = meters[0].get("pod")
            if not self._market_supply_point_id:
                raise UpdateFailed("No electricitySupplyPoints found for property.")
            return self._market_supply_point_id
        except Exception as e:
            raise UpdateFailed(f"Error parsing meters: {e}")

    async def _async_fetch_usage(self):
        """Fetch the last HISTORY_DAYS of daily usage, broken out by F1/F2/F3."""
        import aiohttp
        from datetime import datetime, timedelta

        token = await self._async_get_token()
        property_id = await self._async_get_property_id()
        msp_id = await self._async_get_market_supply_point()

        await self._async_get_timezone()

        # Align the window to local midnights so every returned day is complete.
        today = datetime.now(self._timezone).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_at = dt_util.as_utc(today)
        start_at = dt_util.as_utc(today - timedelta(days=HISTORY_DAYS))

        payload = {
            "operationName": "GetSmartUsage",
            "variables": {
                "propertyId": property_id,
                "timezone": TIMEZONE,
                "startAt": start_at.isoformat().replace("+00:00", "Z"),
                "endAt": end_at.isoformat().replace("+00:00", "Z"),
                "utilityFilters": [
                    {
                        "electricityFilters": {
                            "readingFrequencyType": "DAY_INTERVAL",
                            "marketSupplyPointId": msp_id,
                            "readingDirection": "CONSUMPTION",
                        }
                    }
                ],
            },
            "query": GET_SMART_USAGE_QUERY,
        }
        headers = {"Authorization": token}

        async with aiohttp.ClientSession() as session:
            async with session.post(API_BASE, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Failed to get usage: HTTP {resp.status}")
                data = await resp.json()

        try:
            edges = data["data"]["property"]["measurements"]["edges"]
            readings = parse_daily_readings(edges, self._timezone)
        except Exception as e:
            raise UpdateFailed(f"Error parsing usage data: {e}")

        if not readings:
            return {
                **{k: 0.0 for k in SENSOR_TYPES.keys()},
                "measurement_date": None,
                "readings": [],
            }

        latest = readings[-1]
        return {
            **{k: latest[k] for k in SENSOR_TYPES.keys()},
            "measurement_date": latest["start"].astimezone(self._timezone).date().isoformat(),
            "readings": readings,
        }

    async def _async_update_data(self):
        """Fetch the readings, import them as statistics and return the latest values."""
        data = await self._async_fetch_usage()
        await async_import_statistics(
            self.hass, self._account_number, data["readings"]
        )
        return data

    async def _async_get_gas_pdr(self):
        """Return the PDR of the gas supply point, or None if there is no gas supply."""
        if self._gas_pdr:
            return self._gas_pdr

        import aiohttp

        token = await self._async_get_token()
        property_id = await self._async_get_property_id()
        payload = {
            "operationName": "GetGasSupplyPoints",
            "variables": {"propertyId": property_id},
            "query": GET_GAS_SUPPLY_POINTS_QUERY,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_BASE, json=payload, headers={"Authorization": token}
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Failed to get gas supply points: HTTP {resp.status}")
                data = await resp.json()

        try:
            points = data["data"]["property"]["gasSupplyPoints"]
            smart = [p for p in points if p.get("isSmartMeter")]
            chosen = (smart or points or [None])[0]
            self._gas_pdr = chosen["pdr"] if chosen else None
            return self._gas_pdr
        except Exception as e:
            raise UpdateFailed(f"Error parsing gas supply points: {e}")

    async def async_import_gas_statistics(self):
        """Import monthly gas readings as statistics; does nothing without a gas supply."""
        import aiohttp
        from datetime import datetime

        pdr = await self._async_get_gas_pdr()
        if pdr is None:
            return

        token = await self._async_get_token()
        timezone = await self._async_get_timezone()
        today = datetime.now(timezone).date()
        payload = {
            "operationName": "GetGasReadings",
            "variables": {
                "accountNumber": self._account_number,
                "pdr": pdr,
                "dateFrom": (today - timedelta(days=GAS_HISTORY_DAYS)).isoformat(),
                "dateTo": today.isoformat(),
            },
            "query": GET_GAS_READINGS_QUERY,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_BASE, json=payload, headers={"Authorization": token}
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Failed to get gas readings: HTTP {resp.status}")
                data = await resp.json()

        try:
            readings = parse_gas_readings(data["data"]["gasMeterReadings"]["edges"])
        except Exception as e:
            raise UpdateFailed(f"Error parsing gas readings: {e}")

        await async_import_gas_statistics(
            self.hass, self._account_number, readings, timezone
        )