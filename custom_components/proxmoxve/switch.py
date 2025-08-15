"""Support for switches."""

from __future__ import annotations

from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .pve import PVEDataUpdateCoordinator, PowerAction
from .entity import  PVEVMEntity

VM_SWITCHS: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="vm_power",
        translation_key="vm_power",
        icon="mdi:power",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    
    coordinator: PVEDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    cache_qemus = set()
    cache_lxcs = set() 

    def _on_update():

        dev: list[SwitchEntity] = []
 
        for id, qemu in coordinator.data.qemus.items():
            if id is None or id in cache_qemus:
                continue
            cache_qemus.add(id)
            for description in VM_SWITCHS:
                dev.append(PVEQemuSwitch(
                    hass,
                    description=description,
                    entry=entry,
                    coordinator=coordinator,
                    data=qemu
                ))
        
        for id, lxc in coordinator.data.lxcs.items():
            if id is None or id in cache_lxcs:
                continue
            cache_lxcs.add(id)
            for description in VM_SWITCHS:
                dev.append(PVELXCSwitch(
                    hass,
                    description=description,
                    entry=entry,
                    coordinator=coordinator,
                    data=lxc
                ))
            
        if dev:
            async_add_entities(dev)

    coordinator.async_add_listener(_on_update)

class PVEQemuSwitch(PVEVMEntity, SwitchEntity):

    def __init__(
        self,
        hass,
        description: SwitchEntityDescription,
        entry: ConfigEntry,
        coordinator: PVEDataUpdateCoordinator,
        data: dict
    ) -> None:
        super().__init__(hass, description, entry, coordinator, data)
    
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self.coordinator.data.qemus.get(self.vmid, {}).get("status") == "paused":
            await self.coordinator.async_qemu_power(action=PowerAction.RESUME, node=self.node, vm=self.vmid)
        else:
            await self.coordinator.async_qemu_power(action=PowerAction.ON, node=self.node, vm=self.vmid)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.async_qemu_power(action=PowerAction.OFF, node=self.node, vm=self.vmid)

    @property
    def is_on(self) -> bool:
        """Return True if switch is on."""
        data = self.coordinator.data.qemus.get(self.vmid)
        if not data:
            return None
        status = data.get("status", None)
        if not status:
            return None
        return status == "running"

class PVELXCSwitch(PVEVMEntity, SwitchEntity):

    def __init__(
        self,
        hass,
        description: SwitchEntityDescription,
        entry: ConfigEntry,
        coordinator: PVEDataUpdateCoordinator,
        data: dict
    ) -> None:
        super().__init__(hass, description, entry, coordinator, data)
    
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self.coordinator.data.qemus.get(self.vmid, {}).get("status") == "paused":
            await self.coordinator.async_lxc_power(action=PowerAction.RESUME, node=self.node, vm=self.vmid)
        else:
            await self.coordinator.async_lxc_power(action=PowerAction.ON, node=self.node, vm=self.vmid)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.async_lxc_power(action=PowerAction.OFF, node=self.node, vm=self.vmid)

    @property
    def is_on(self) -> bool:
        """Return True if switch is on."""
        data = self.coordinator.data.lxcs.get(self.vmid)
        if not data:
            return None
        status = data.get("status", None)
        if not status:
            return None
        return status == "running"