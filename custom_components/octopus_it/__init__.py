import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    API_BASE,
    LOGIN_QUERY,
    GET_PROPERTIES_QUERY,
    GET_METERS_QUERY,
    GET_SMART_USAGE_QUERY,
    DEFAULT_SCAN_INTERVAL,
    SENSOR_TYPES, GET_ACCOUNT_LIST_QUERY,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Octopus Italy from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = OctopusCoordinator(hass, email, password, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

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
        self._token_expiry = None
        self._account_number = None
        self._property_id = None
        self._market_supply_point_id = None

    async def _async_get_token(self):
        """Obtain or refresh JWT token."""
        import aiohttp

        if self._token and self._token_expiry:
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
            self._token_expiry = token_data["refreshExpiresIn"]
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
        """Fetch the last 1 day of usage, broken out by F1/F2/F3."""
        import aiohttp
        from datetime import datetime, timedelta, timezone

        token = await self._async_get_token()
        property_id = await self._async_get_property_id()
        msp_id = await self._async_get_market_supply_point()

        now = datetime.now(timezone.utc)
        end_at = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_at = end_at - timedelta(days=7)

        payload = {
            "operationName": "GetSmartUsage",
            "variables": {
                "propertyId": property_id,
                "timezone": "Europe/Rome",
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
            if not edges:
                return {k: 0.0 for k in SENSOR_TYPES.keys()}

            node = edges[-1]["node"]
            total = float(node.get("value", 0.0))
            measurement_date = node.get("startAt", "")
            stats = node.get("metaData", {}).get("statistics", [])
            f_values = {"F1": 0.0, "F2": 0.0, "F3": 0.0}
            for entry in stats:
                label = entry.get("label")
                val = float(entry.get("value", 0.0))
                if label in f_values:
                    f_values[label] = val

            return {
                "daily_total": total,
                "daily_f1": f_values["F1"],
                "daily_f2": f_values["F2"],
                "daily_f3": f_values["F3"],
                "measurement_date": measurement_date,
            }
        except Exception as e:
            raise UpdateFailed(f"Error parsing usage data: {e}")

    async def _async_update_data(self):
        """Fetch data from the API and return a dict of latest values."""
        return await self._async_fetch_usage()