from datetime import timedelta
import datetime
from enum import StrEnum
import logging
from asyncio.exceptions import CancelledError
from custom_components.proxmoxve.utils import to_pecent
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from proxmoxer import ProxmoxAPI
from homeassistant.util import dt as dt_util
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
)
from .const import DOMAIN
import urllib3
import paramiko
from io import StringIO

urllib3.disable_warnings()

_LOGGER = logging.getLogger(__name__)


class PowerAction(StrEnum):
    ON = "on"
    OFF = "off"
    SUSPEND = "suspend"
    RESET = "reset"
    SHUTDOWN = "shutdown"
    REBOOT = "reboot"
    RESUME = "resume"


class PVEData:
    nodes = dict()
    qemus = dict()
    lxcs = dict()
    disks = dict()
    time: datetime


def async_get_or_create_device(hass, entry_id, node=None, vm=None):
    if not entry_id:
        return None

    dev_reg = dr.async_get(hass)

    if node:
        name = node.get("node", None)
        if not name:
            return None
        return dev_reg.async_get_or_create(
            config_entry_id=entry_id,
            identifiers={(DOMAIN, entry_id, "node", name)},
            manufacturer="PVE",
            model=node.get("type"),
            name="PVE",
        )

    if vm:
        vmid = vm.get("vmid", None)
        if not vmid:
            return None
        node_name = vm.get("node", None)

        return dev_reg.async_get_or_create(
            config_entry_id=entry_id,
            identifiers={(DOMAIN, entry_id, "vm", vmid)},
            name=vm.get("name"),
            manufacturer="PVE",
            model=vm.get("type"),
            via_device=(DOMAIN, entry_id, "node", node_name),
        )

    return None


class PVEDataUpdateCoordinator(DataUpdateCoordinator):
    """The class for handling the data retrieval."""

    def __init__(self, hass, config):
        """Initialize the data object."""
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=2)
        )
        self._config = config
        self._conn = None
        self._ssh_client = None
        self._ssh_connected = False

    async def _async_update_data(self):
        try:
            return await self.hass.async_add_executor_job(self._update_data)
        except CancelledError:
            _LOGGER.debug("Cancel update")

    def _connect(self):
        self._conn = ProxmoxAPI(
            host=self._config.get(CONF_HOST),
            backend="https",
            port=self._config.get(CONF_PORT, 8006),
            user=self._config.get(CONF_USERNAME),
            password=self._config.get(CONF_PASSWORD),
            verify_ssl=self._config.get(CONF_VERIFY_SSL, False),
            timeout=5,
        )
        
    def _connect_ssh(self):
        """Establish SSH connection to the Proxmox node."""
        if self._ssh_connected:
            return True
            
        try:
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh_client.connect(
                hostname=self._config.get(CONF_HOST),
                port=self._config.get("ssh_port", 22),
                username=self._config.get(CONF_USERNAME, "root").split('@')[0],
                password=self._config.get(CONF_PASSWORD, ""),
                timeout=5,
            )
            self._ssh_connected = True
            _LOGGER.debug("SSH connection established successfully")
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to establish SSH connection: {e}")
            self._ssh_connected = False
            return False
            
    def _get_disk_info(self):
        """Get disk model and temperature via SSH."""
        if not self._ssh_connected:
            if not self._connect_ssh():
                return None
                
        try:
            # List disks - 使用更可靠的方法获取磁盘列表
            stdin, stdout, stderr = self._ssh_client.exec_command("find /dev -name 'sd*' -not -path '*/mapper/*' | sort")
            output = stdout.read().decode().strip()
            
            # 确保即使只有一个磁盘也能正确处理
            if not output:
                _LOGGER.warning("No disks found")
                return {}
                
            disks = output.split("\n")
            
            # 过滤掉分区（带数字的设备名）
            main_disks = []
            for disk in disks:
                disk_name = disk.split("/")[-1]
                # 只保留不包含数字的设备名（主磁盘设备）
                if disk.strip() and not any(c.isdigit() for c in disk_name):
                    main_disks.append(disk)
            
            _LOGGER.debug(f"Found {len(main_disks)} main disks (excluding partitions): {main_disks}")
            
            disk_info = {}
            for disk in main_disks:
                # 首先尝试获取磁盘型号
                stdin, stdout, stderr = self._ssh_client.exec_command(
                    f"lsblk -o NAME,MODEL,VENDOR -dn {disk}"
                )
                model_output = stdout.read().decode().strip()
                
                model_family = "Unknown"
                device_model = "Unknown"
                temperature = None
                
                # 从lsblk输出中提取型号
                if model_output:
                    parts = model_output.split()
                    if len(parts) > 1:
                        device_model = " ".join(parts[1:]).strip()
                
                # 如果lsblk没有提供足够信息，尝试使用smartctl
                if device_model == "Unknown":
                    stdin, stdout, stderr = self._ssh_client.exec_command(
                        f"smartctl -a {disk} | grep -E \"Model|Family\""
                    )
                    output = stdout.read().decode()
                    
                    lines = output.strip().split("\n")
                    for line in lines:
                        if "Model Family" in line:
                            model_family = line.split("Model Family:")[1].strip()
                        elif "Device Model" in line:
                            device_model = line.split("Device Model:")[1].strip()
                
                # 获取温度信息 - 使用更可靠的方法
                stdin, stdout, stderr = self._ssh_client.exec_command(
                    f"smartctl -a {disk} | grep -E \"Temperature_Celsius|Current Temperature\""
                )
                temp_output = stdout.read().decode()
                
                # 如果第一种方法没有找到温度数据，尝试备用方法
                if not temp_output.strip():
                    stdin, stdout, stderr = self._ssh_client.exec_command(
                        f"smartctl -a {disk} | grep -E \"Temperature:|Airflow_Temperature\""
                    )
                    temp_output = stdout.read().decode()
                
                # 提取温度信息
                for line in temp_output.strip().split("\n"):
                    if "Temperature_Celsius" in line:
                        # 使用固定位置（第10个字段）获取温度值
                        parts = line.strip().split()
                        if len(parts) >= 10:
                            try:
                                # 直接使用第10个字段（索引9）获取温度
                                temperature = int(parts[9])
                                # 如果获取到的温度是0，可能是格式问题，尝试其他方法
                                if temperature == 0:
                                    # 尝试使用最后一个字段
                                    temperature = int(parts[-1])
                            except ValueError:
                                temperature = None
                
                # Use device model as the primary name, fallback to model family
                model = device_model if device_model != "Unknown" else model_family
                
                disk_info[disk] = {
                    "model": model,
                    "temperature": temperature
                }
            
            return disk_info
        except Exception as e:
            _LOGGER.error(f"Failed to get disk info: {e}")
            return None

    def _update_data(self):
        data = PVEData()
        try:
            if not self._conn:
                self._connect()

            resources = self._conn.cluster.resources.get()
            data.time = dt_util.utcnow()
            _LOGGER.debug(resources)

            for res in resources:
                if res.get("type", None) != "node":
                    continue
                node, id = self._get_node_info(res)
                data.nodes[id] = node

            for res in resources:
                res_type = res.get("type", None)
                if res_type == "lxc":
                    lxc, id = self._get_lxc_info(res, data.nodes)
                    data.lxcs[id] = lxc
                elif res_type == "qemu":
                    qemu, id = self._get_qemu_info(res, data.nodes)
                    data.qemus[id] = qemu
                elif res_type == "storage":
                    pass
                elif res_type == "sdn":
                    pass

            data.disks = self._get_disk_info()
            return data
        except Exception as error:
            _LOGGER.exception(error)
            # 返回一个空的PVEData对象，避免后续访问None
            data.disks = self._get_disk_info()
            return data

    def _get_lxc_info(self, lxc, nodes):
        lxc = self._get_usage_info(lxc, nodes)
        return lxc, lxc.get("vmid")

    def _get_qemu_info(self, qemu, nodes):
        qemu = self._get_usage_info(qemu, nodes)
        return qemu, qemu.get("vmid")

    def _get_node_info(self, node):
        node = self._get_usage_info(node)
        
        # 获取节点温度信息
        try:
            node_name = node.get("node")
            if node_name:
                # 通过SSH执行sensors -j命令获取温度数据
                _LOGGER.debug(f"尝试通过SSH获取节点 {node_name} 的温度信息")
                
                # 确保SSH连接已建立
                if not self._connect_ssh():
                    _LOGGER.warning("SSH连接失败，无法获取温度信息")
                    return node, node.get("node")
                
                # 执行sensors -j命令
                stdin, stdout, stderr = self._ssh_client.exec_command("sensors -j")
                sensors_output = stdout.read().decode("utf-8")
                stderr_output = stderr.read().decode("utf-8")
                
                if stderr_output:
                    _LOGGER.warning(f"执行sensors命令时出错: {stderr_output}")
                
                if sensors_output:
                    _LOGGER.debug(f"获取到温度数据结果，开始处理")
                    
                    # 解析JSON格式的温度数据
                    import json
                    try:
                        sensors_data = json.loads(sensors_output)
                        _LOGGER.debug(f"成功解析温度数据，找到传感器: {list(sensors_data.keys())}")
                        
                        # 提取温度数据
                        temperatures = {}
                        
                        # 处理CPU温度
                        if "coretemp-isa-0000" in sensors_data:
                            cpu_data = sensors_data["coretemp-isa-0000"]
                            # 获取Package温度
                            if "Package id 0" in cpu_data:
                                package = cpu_data["Package id 0"]
                                if "temp1_input" in package:
                                    temperatures["cpu_package"] = package["temp1_input"]
                            
                            # 获取各个核心温度
                            core_temps = []
                            for key, value in cpu_data.items():
                                if key.startswith("Core "):
                                    for temp_key, temp_value in value.items():
                                        if temp_key.endswith("_input"):
                                            core_temps.append(temp_value)
                                            temperatures[f"cpu_{key.lower()}"] = temp_value
                            
                            # 计算CPU平均温度
                            if core_temps:
                                temperatures["cpu_avg"] = sum(core_temps) / len(core_temps)
                        
                        # 处理主板温度
                        for sensor_key in sensors_data:
                            # 尝试查找主板温度传感器
                            if sensor_key.startswith("acpitz-acpi") or "motherboard" in sensor_key.lower():
                                acpi_data = sensors_data[sensor_key]
                                # 遍历所有可能的温度传感器
                                for temp_key in acpi_data:
                                    if temp_key.startswith("temp"):
                                        temp_data = acpi_data[temp_key]
                                        if isinstance(temp_data, dict) and "temp1_input" in temp_data:
                                            temperatures["motherboard"] = temp_data["temp1_input"]
                                            break
                                        elif isinstance(temp_data, dict) and any(k.endswith("_input") for k in temp_data):
                                            # 找到第一个输入温度
                                            for k, v in temp_data.items():
                                                if k.endswith("_input"):
                                                    temperatures["motherboard"] = v
                                                    break
                                            break
                                if "motherboard" in temperatures:
                                    break
                        
                        # 处理NVMe温度
                        if "nvme-pci-0600" in sensors_data:
                            nvme_data = sensors_data["nvme-pci-0600"]
                            if "Composite" in nvme_data and "temp1_input" in nvme_data["Composite"]:
                                temperatures["nvme"] = nvme_data["Composite"]["temp1_input"]
                        
                        # 添加到节点数据中
                        if temperatures:
                            node["temperatures"] = temperatures
                            _LOGGER.debug(f"找到的温度数据: {temperatures}")
                            
                            # 设置CPU温度为主要温度指标
                            if "cpu_package" in temperatures:
                                node["cpu_temperature"] = temperatures["cpu_package"]
                            elif "cpu_avg" in temperatures:
                                node["cpu_temperature"] = temperatures["cpu_avg"]
                            elif temperatures:
                                # 如果没有找到CPU温度，使用第一个温度作为默认值
                                node["cpu_temperature"] = next(iter(temperatures.values()))
                            
                            # 添加其他温度传感器
                            if "motherboard" in temperatures:
                                node["motherboard_temperature"] = temperatures["motherboard"]
                            else:
                                # 如果没有找到主板温度，尝试使用其他温度传感器
                                for key, value in temperatures.items():
                                    if "board" in key.lower() or "sys" in key.lower():
                                        node["motherboard_temperature"] = value
                                        break
                            
                            if "nvme" in temperatures:
                                node["nvme_temperature"] = temperatures["nvme"]
                            else:
                                # 尝试查找其他NVMe温度传感器
                                for key, value in temperatures.items():
                                    if "nvme" in key.lower() or "ssd" in key.lower():
                                        node["nvme_temperature"] = value
                                        break
                    except Exception as e:
                        _LOGGER.warning(f"处理温度数据时发生错误: {e}")
        except Exception as e:
            _LOGGER.warning(f"获取节点温度失败: {e}")
            import traceback
            _LOGGER.debug(f"详细错误: {traceback.format_exc()}")
            
        return node, node.get("node")

    def _get_usage_info(self, res, nodes=None):
        res["cpu_usage"] = to_pecent(res.get("cpu"))
        res["mem_usage"] = self._usage_pecent(res, "mem", "maxmem")
        res["disk_usage"] = self._usage_pecent(res, "disk", "maxdisk")
        if nodes:
            node = nodes.get(res.get("node"), {})
            res["node_maxcpu"] = node.get("maxcpu")
            cpu = res.get("cpu")
            maxcpu = res.get("maxcpu")
            node_maxcpu = res.get("node_maxcpu")
            res["node_cpu_usage"] = (
                to_pecent(cpu * maxcpu / node_maxcpu)
                if cpu is not None and maxcpu is not None and node_maxcpu
                else None
            )
            res["node_maxmem"] = node.get("maxmem")
            res["node_mem_usage"] = self._usage_pecent(res, "mem", "node_maxmem")
        return res

    def _usage_pecent(self, data, key_a, key_b):
        a = data.get(key_a)
        b = data.get(key_b)
        if a is None or not b:
            return None
        return to_pecent(a / b)

    async def async_node_power(self, action: PowerAction, node: str):
        await self.hass.async_add_executor_job(self.node_power, action, node)

    async def async_qemu_power(self, action: PowerAction, node: str, vm: str):
        await self.hass.async_add_executor_job(self.qemu_power, action, node, vm)

    async def async_lxc_power(self, action: PowerAction, node: str, vm: str):
        await self.hass.async_add_executor_job(self.lxc_power, action, node, vm)

    def node_power(self, action: PowerAction, node: str):
        if not node or not action:
            return

        if action == PowerAction.REBOOT:
            self._conn.nodes(node).status.post(command="reboot")
            return
        if action == PowerAction.SHUTDOWN:
            self._conn.nodes(node).status.post(command="shutdown")
            return

    def qemu_power(self, action: PowerAction, node: str, vm: str):
        if not node or not vm or not action:
            return

        if action == PowerAction.ON:
            self._conn.nodes(node).qemu(vm).status.start.post()
            return
        if action == PowerAction.OFF:
            self._conn.nodes(node).qemu(vm).status.stop.post()
            return
        if action == PowerAction.SUSPEND:
            self._conn.nodes(node).qemu(vm).status.suspend.post()
            return
        if action == PowerAction.RESUME:
            self._conn.nodes(node).qemu(vm).status.resume.post()
            return
        if action == PowerAction.RESET:
            self._conn.nodes(node).qemu(vm).status.reset.post()
            return
        if action == PowerAction.REBOOT:
            self._conn.nodes(node).qemu(vm).status.reboot.post()
            return
        if action == PowerAction.SHUTDOWN:
            self._conn.nodes(node).qemu(vm).status.shutdown.post()
            return

    def lxc_power(self, action: PowerAction, node: str, vm: str):
        if not node or not vm or not action:
            return

        if action == PowerAction.ON:
            self._conn.nodes(node).lxc(vm).status.start.post()
            return
        if action == PowerAction.OFF:
            self._conn.nodes(node).lxc(vm).status.stop.post()
            return
        if action == PowerAction.SUSPEND:
            self._conn.nodes(node).lxc(vm).status.suspend.post()
            return
        if action == PowerAction.RESUME:
            self._conn.nodes(node).lxc(vm).status.resume.post()
            return
        if action == PowerAction.REBOOT:
            self._conn.nodes(node).lxc(vm).status.reboot.post()
            return
        if action == PowerAction.SHUTDOWN:
            self._conn.nodes(node).lxc(vm).status.shutdown.post()
            return
