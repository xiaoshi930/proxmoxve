from __future__ import annotations

import logging

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .pve import async_get_or_create_device, PVEDataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PVENodeEntity(CoordinatorEntity[PVEDataUpdateCoordinator]):

    _attr_has_entity_name = True
    
    entity_description: EntityDescription

    def __init__(self, hass, description, entry, coordinator, data):
        super().__init__(coordinator)
        self.hass = hass
        self.entity_description = description
        self.node = data.get("node")
        self._attr_unique_id = "_".join(
            [
                DOMAIN,
                entry.entry_id,
                "node",
                self.node,
                self.entity_description.key
            ]
        )
        device = async_get_or_create_device(
            hass=self.hass,
            entry_id=entry.entry_id,
            node=data
        )
        
        self._attr_device_info = DeviceInfo(
            identifiers=device.identifiers,
        )
        
class PVEVMEntity(CoordinatorEntity[PVEDataUpdateCoordinator]):

    _attr_has_entity_name = True
    
    entity_description: EntityDescription

    def __init__(self, hass, description, entry, coordinator, data):
        super().__init__(coordinator)
        self.hass = hass
        self.entity_description = description
        self.node = data.get("node")
        self.vmid = data.get("vmid")
        self._attr_unique_id = "_".join(
            [
                DOMAIN,
                entry.entry_id,
                "vm",
                self.node,
                str(self.vmid),
                self.entity_description.key
            ]
        )
        device = async_get_or_create_device(
            hass=self.hass,
            entry_id=entry.entry_id,
            vm=data,
        )
        
        self._attr_device_info = DeviceInfo(
            identifiers=device.identifiers,
        )
