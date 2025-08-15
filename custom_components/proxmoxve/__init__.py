from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.start import async_at_started
from .pve import PVEDataUpdateCoordinator
from .const import DOMAIN

PLATFORMS = [Platform.SENSOR, Platform.BUTTON, Platform.SWITCH]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    config = entry.data
    pve = PVEDataUpdateCoordinator(hass, dict(config))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = pve

    async def _async_finish_startup(hass: HomeAssistant) -> None:
        """Run this only when HA has finished its startup."""
        await pve.async_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Don't fetch data during startup, this will slow down the overall startup dramatically
    async_at_started(hass, _async_finish_startup)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if len(hass.config_entries.async_entries(DOMAIN)) == 0:
            hass.data.pop(DOMAIN)
    
    return unload_ok
