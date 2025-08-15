from __future__ import annotations

from dataclasses import dataclass
import logging


from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTime,
    UnitOfDataRate,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from .entity import PVENodeEntity, PVEVMEntity
from .pve import PVEDataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MIN_STATISTICS_SEC = 15
MAX_STATISTICS_SEC = 25


@dataclass(frozen=True, kw_only=True)
class PVESensorEntityDescription(SensorEntityDescription):
    statistics: bool = False
    data_key: str


SENSORS: tuple[PVESensorEntityDescription, ...] = (
    PVESensorEntityDescription(
        key="disk_usage",
        translation_key="disk_usage",
        icon="mdi:database",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        data_key="disk_usage",
    ),
    PVESensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        data_key="uptime",
    ),
)
NODE_SENSORS: tuple[PVESensorEntityDescription, ...] = SENSORS + (
    PVESensorEntityDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        icon="mdi:cpu-64-bit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        data_key="cpu_usage",
    ),
    PVESensorEntityDescription(
        key="mem_usage",
        translation_key="mem_usage",
        icon="mdi:memory",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        data_key="mem_usage",
    ),
    PVESensorEntityDescription(
        key="cpu_temperature",
        translation_key="cpu_temperature",
        icon="mdi:cpu-64-bit",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        data_key="cpu_temperature",
    ),
    PVESensorEntityDescription(
        key="motherboard_temperature",
        translation_key="motherboard_temperature",
        icon="mdi:desktop-tower-monitor",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        data_key="motherboard_temperature",
    ),
    PVESensorEntityDescription(
        key="nvme_temperature",
        translation_key="nvme_temperature",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        data_key="nvme_temperature",
    ),
    PVESensorEntityDescription(
        key="disk_model",
        translation_key="disk_model",
        icon="mdi:harddisk",
        data_key="disks",
    ),
    PVESensorEntityDescription(
        key="disk_temperature",
        translation_key="disk_temperature",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        data_key="disks",
    ),
)
VM_SENSORS: tuple[PVESensorEntityDescription, ...] = SENSORS + (
    PVESensorEntityDescription(
        key="vm_cpu_usage",
        translation_key="vm_cpu_usage",
        icon="mdi:cpu-64-bit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        data_key="cpu_usage",
    ),
    PVESensorEntityDescription(
        key="vm_mem_usage",
        translation_key="vm_mem_usage",
        icon="mdi:memory",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        data_key="mem_usage",
    ),
    PVESensorEntityDescription(
        key="node_cpu_usage",
        translation_key="node_cpu_usage",
        icon="mdi:cpu-64-bit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        data_key="node_cpu_usage",
    ),
    PVESensorEntityDescription(
        key="node_mem_usage",
        translation_key="node_mem_usage",
        icon="mdi:memory",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        data_key="node_mem_usage",
    ),
    PVESensorEntityDescription(
        key="netin",
        translation_key="netin",
        icon="mdi:download-network",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        suggested_display_precision=2,
        statistics=True,
        data_key="netin",
    ),
    PVESensorEntityDescription(
        key="netout",
        translation_key="netout",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        suggested_display_precision=2,
        statistics=True,
        data_key="netout",
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
    cache_disks = set()  # 添加磁盘缓存集合

    def _on_update():
        dev: list[SensorEntity] = []
        if coordinator.data is None:
            _LOGGER.warning("Coordinator data is None, skipping update")
            return
            
        # 处理磁盘传感器
        if coordinator.data.disks:
            _LOGGER.debug(f"Found {len(coordinator.data.disks)} disks: {list(coordinator.data.disks.keys())}")
            
            # 获取磁盘温度传感器描述
            disk_temp_desc = next((d for d in NODE_SENSORS if d.key == "disk_temperature"), None)
            
            if disk_temp_desc:
                # 为每个磁盘创建温度传感器
                for disk_path, disk_info in coordinator.data.disks.items():
                    # 检查磁盘是否已经在缓存中
                    if disk_path in cache_disks:
                        _LOGGER.debug(f"Disk {disk_path} already in cache, skipping")
                        continue
                        
                    # 记录磁盘信息，无论是否有温度数据
                    _LOGGER.debug(f"Processing disk {disk_path} with model {disk_info.get('model')}, temperature: {disk_info.get('temperature')}")
                    
                    # 添加到缓存
                    cache_disks.add(disk_path)
                    
                    # 为所有磁盘创建传感器，即使没有温度数据
                    _LOGGER.debug(f"Creating temperature sensor for disk {disk_path}")
                    
                    # 创建传感器实体
                    sensor = PVENodeSensor(
                        hass,
                        description=disk_temp_desc,
                        entry=entry,
                        coordinator=coordinator,
                        data={"node": list(coordinator.data.nodes.keys())[0] if coordinator.data.nodes else "unknown"}
                    )
                    # 设置磁盘路径，这会影响 unique_id 的生成
                    sensor.disk_path = disk_path
                    # 记录生成的唯一ID，用于调试
                    _LOGGER.debug(f"Created disk temperature sensor with unique_id: {sensor.unique_id}")
                    dev.append(sensor)
            
        for id, node in coordinator.data.nodes.items():
            if id is None or id in cache_nodes:
                continue
            cache_nodes.add(id)
            for description in NODE_SENSORS:
                # 跳过磁盘温度传感器，因为我们已经为每个磁盘创建了单独的传感器
                if description.key in ["disk_temperature", "disk_model"]:
                    continue
                dev.append(
                    PVENodeSensor(
                        hass,
                        description=description,
                        entry=entry,
                        coordinator=coordinator,
                        data=node,
                    )
                )
        for id, qemu in coordinator.data.qemus.items():
            if id is None or id in cache_qemus:
                continue
            cache_qemus.add(id)
            for description in VM_SENSORS:
                dev.append(
                    PVEQemuSensor(
                        hass,
                        description=description,
                        entry=entry,
                        coordinator=coordinator,
                        data=qemu,
                    )
                )

        for id, lxc in coordinator.data.lxcs.items():
            if id is None or id in cache_lxcs:
                continue
            cache_lxcs.add(id)
            for description in VM_SENSORS:
                dev.append(
                    PVELXCSensor(
                        hass,
                        description=description,
                        entry=entry,
                        coordinator=coordinator,
                        data=lxc,
                    )
                )

        if dev:
            async_add_entities(dev)

    coordinator.async_add_listener(_on_update)


class PVEVMSensorEntity(PVEVMEntity, SensorEntity):
    def __init__(self, hass, description, entry, coordinator, data):
        super().__init__(hass, description, entry, coordinator, data)
        if self.entity_description.statistics:
            self._last_value = None
            self._last_time = None

    def _get_data(self):
        """data"""

    def _get_value(self):
        if data := self._get_data():
            return data.get(self.entity_description.data_key, None)
        return None

    def _should_update(self):
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        if (
            self.entity_description.statistics
            and self._last_time is not None
            and (self.coordinator.data.time - self._last_time).total_seconds()
            < MIN_STATISTICS_SEC
            and self._last_value is not None
            and self._get_value() == self._last_value
        ):
            return
        super()._handle_coordinator_update()

    @property
    def native_value(self):
        value = self._get_value()
        if not self.entity_description.statistics:
            return value
        
        last_value = self._last_value
        last_time = self._last_time
        this_time = self.coordinator.data.time
        self._last_time = this_time
        self._last_value = value
        if (
            last_value is None
            or last_time is None
            or value is None
            or last_value > value
        ):
            return None
        delta_sec = (this_time - last_time).total_seconds()
        if delta_sec > MAX_STATISTICS_SEC or delta_sec <= 0:
            return None
        return round((value - last_value) / delta_sec, 0)


class PVEQemuSensor(PVEVMSensorEntity):
    def __init__(self, hass, description, entry, coordinator, data):
        super().__init__(hass, description, entry, coordinator, data)

    def _get_data(self):
        return self.coordinator.data.qemus.get(self.vmid, None)


class PVELXCSensor(PVEVMSensorEntity):
    def __init__(self, hass, description, entry, coordinator, data):
        super().__init__(hass, description, entry, coordinator, data)

    def _get_data(self):
        return self.coordinator.data.lxcs.get(self.vmid, None)


class PVENodeSensor(PVENodeEntity, SensorEntity):
    def __init__(self, hass, description, entry, coordinator, data):
        super().__init__(hass, description, entry, coordinator, data)
        self.disk_path = None
        
    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        # 如果是磁盘温度传感器，则在 unique_id 中包含磁盘路径
        if self.entity_description.key == "disk_temperature" and self.disk_path:
            # 从路径中提取磁盘名称（例如 sda）
            disk_name = self.disk_path.split("/")[-1]
            return "_".join(
                [
                    DOMAIN,
                    self.coordinator.config_entry.entry_id,
                    "node",
                    self.node,
                    self.entity_description.key,
                    disk_name  # 添加磁盘名称到 unique_id
                ]
            )
        # 对于其他传感器，使用默认的 unique_id
        return self._attr_unique_id
        
    @property
    def name(self):
        """Return the name of the sensor."""
        if self.entity_description.key == "disk_temperature" and self.coordinator.data.disks:
            # 直接使用磁盘名称（如sda、sdb）作为实体名称
            if self.disk_path and self.disk_path in self.coordinator.data.disks:
                # 从路径中提取磁盘名称（例如 /dev/sda 提取为 sda）
                disk_name = self.disk_path.split("/")[-1]
                return f"磁盘{disk_name}"
        return super().name

    @property
    def native_value(self):
        if self.entity_description.key == "disk_temperature":
            # 处理磁盘温度信息
            if not self.coordinator.data.disks:
                _LOGGER.debug("No disk information available")
                return None
                
            # 确保磁盘路径已设置
            if self.disk_path is None:
                _LOGGER.debug("Disk path is not set")
                return None
                
            # 确保磁盘信息存在
            if self.disk_path not in self.coordinator.data.disks:
                _LOGGER.debug(f"Disk {self.disk_path} not found in available disks: {list(self.coordinator.data.disks.keys())}")
                return None
                
            disk_info = self.coordinator.data.disks[self.disk_path]
            temperature = disk_info.get("temperature")
            return temperature if temperature is not None else "未知"
        else:
            # 处理其他节点信息
            if data := self.coordinator.data.nodes.get(self.node, None):
                return data.get(self.entity_description.data_key, None)
            return None
