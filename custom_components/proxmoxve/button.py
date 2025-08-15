from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN
from .pve import PVEDataUpdateCoordinator, PowerAction
from .entity import PVENodeEntity, PVEVMEntity


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PVEButtonEntityDescription(ButtonEntityDescription):
    action: PowerAction

NODE_BUTTONS: tuple[PVEButtonEntityDescription, ...] = (
    PVEButtonEntityDescription(
        key="shutdown",
        translation_key="shutdown",
        icon="mdi:power",
        entity_category=EntityCategory.CONFIG,
        action=PowerAction.SHUTDOWN
    ),
    PVEButtonEntityDescription(
        key="reboot",
        translation_key="reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        action=PowerAction.REBOOT
    ),
)

QEMU_BUTTONS: tuple[PVEButtonEntityDescription, ...] = (
    PVEButtonEntityDescription(
        key="suspend",
        translation_key="suspend",
        icon="mdi:pause-circle-outline",
        entity_category=EntityCategory.CONFIG,
        action=PowerAction.SUSPEND
    ),
    PVEButtonEntityDescription(
        key="shutdown",
        translation_key="shutdown",
        icon="mdi:power",
        entity_category=EntityCategory.CONFIG,
        action=PowerAction.SHUTDOWN
    ),
    PVEButtonEntityDescription(
        key="reboot",
        translation_key="reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        action=PowerAction.REBOOT
    ),
    PVEButtonEntityDescription(
        key="reset",
        translation_key="reset",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        action=PowerAction.RESET
    ),
)

LXC_BUTTONS: tuple[PVEButtonEntityDescription, ...] = (
    PVEButtonEntityDescription(
        key="suspend",
        translation_key="suspend",
        icon="mdi:pause-circle-outline",
        entity_category=EntityCategory.CONFIG,
        action=PowerAction.SUSPEND
    ),
    PVEButtonEntityDescription(
        key="shutdown",
        translation_key="shutdown",
        icon="mdi:power",
        entity_category=EntityCategory.CONFIG,
        action=PowerAction.SHUTDOWN
    ),
    PVEButtonEntityDescription(
        key="reboot",
        translation_key="reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        action=PowerAction.REBOOT
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    
    coordinator: PVEDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    cache_nodes = set()
    cache_qemus = set()
    cache_lxcs = set() 

    def _on_update():
        dev: list[ButtonEntity] = []
        for id, node in coordinator.data.nodes.items():
            if id is None or id in cache_nodes:
                continue
            cache_nodes.add(id)
            for description in NODE_BUTTONS:
                dev.append(PVENodeButton(
                    hass,
                    description=description,
                    entry=entry,
                    coordinator=coordinator,
                    data=node
                ))
        for id, qemu in coordinator.data.qemus.items():
            if id is None or id in cache_qemus:
                continue
            cache_qemus.add(id)
            for description in QEMU_BUTTONS:
                dev.append(PVEQemuButton(
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
            for description in LXC_BUTTONS:
                dev.append(PVELXCButton(
                    hass,
                    description=description,
                    entry=entry,
                    coordinator=coordinator,
                    data=lxc
                ))
            
        if dev:
            async_add_entities(dev)

    coordinator.async_add_listener(_on_update)

class PVENodeButton(PVENodeEntity, ButtonEntity):

    def __init__(
        self,
        hass,
        description: PVEButtonEntityDescription,
        entry: ConfigEntry,
        coordinator: PVEDataUpdateCoordinator,
        data: dict
    ) -> None:
        super().__init__(hass, description, entry, coordinator, data)

    async def async_press(self) -> None:
        await self.coordinator.async_node_power(action=self.entity_description.action, node=self.node)


class PVEQemuButton(PVEVMEntity, ButtonEntity):

    def __init__(
        self,
        hass,
        description: PVEButtonEntityDescription,
        entry: ConfigEntry,
        coordinator: PVEDataUpdateCoordinator,
        data: dict
    ) -> None:
        super().__init__(hass, description, entry, coordinator, data)

    async def async_press(self) -> None:
        await self.coordinator.async_qemu_power(action=self.entity_description.action, node=self.node, vm=self.vmid)

class PVELXCButton(PVEVMEntity, ButtonEntity):

    def __init__(
        self,
        hass,
        description: PVEButtonEntityDescription,
        entry: ConfigEntry,
        coordinator: PVEDataUpdateCoordinator,
        data: dict
    ) -> None:
        super().__init__(hass, description, entry, coordinator, data)

    async def async_press(self) -> None:
        await self.coordinator.async_lxc_power(action=self.entity_description.action, node=self.node, vm=self.vmid)

