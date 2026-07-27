"""Sensor platform for BESTIN"""

from __future__ import annotations

from homeassistant.components.sensor import (
    DOMAIN as DOMAIN_SENSOR,
    SensorEntity,
    SensorDeviceClass
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
    UnitOfVolumeFlowRate
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import NEW_SENSOR
from .device import BestinDevice
from .hub import BestinHub

DEVICE_ICON = {
    "light:dcvalue": "mdi:flash",
    "outlet:powercons": "mdi:flash",
    "electric:realtime": "mdi:flash",
    "electric:total": "mdi:lightning-bolt",
    "gas:realtime": "mdi:gas-cylinder",
    "gas:total": "mdi:gas-cylinder",
    "heat:realtime": "mdi:radiator",
    "heat:total": "mdi:thermometer-lines",
    "hotwater:realtime": "mdi:water-boiler",
    "hotwater:total": "mdi:water-boiler",
    "water:realtime": "mdi:water-pump",
    "water:total": "mdi:water-pump",
    # 클라우드 에너지 비교 값 (iparkapp.py). "mine_*"는 가구 총 사용량,
    # "avg_*"는 단지 평균치입니다. const.ENERGY_FRIENDLY_LABELS 참고.
    #
    # BESTIN Energy cloud comparison readings (iparkapp.py). "mine_*" is the
    # household meter total, "avg_*" is the complex-wide neighbor average.
    # See const.ENERGY_FRIENDLY_LABELS.
    "energy:mineelec": "mdi:lightning-bolt",
    "energy:avgelec": "mdi:lightning-bolt-outline",
    "energy:minegas": "mdi:gas-cylinder",
    "energy:avggas": "mdi:gas-cylinder",
    "energy:minewater": "mdi:water-pump",
    "energy:avgwater": "mdi:water-pump",
    "energy:minehwater": "mdi:water-boiler",
    "energy:avghwater": "mdi:water-boiler",
    "energy:mineheat": "mdi:radiator",
    "energy:avgheat": "mdi:radiator",
}

DEVICE_CLASS = {
    "light:dcvalue": SensorDeviceClass.POWER,
    "outlet:cutvalue": SensorDeviceClass.POWER,
    "outlet:powercons": SensorDeviceClass.POWER,
    "electric:realtime": SensorDeviceClass.POWER,
    "electric:total": SensorDeviceClass.ENERGY,
    "gas:total": SensorDeviceClass.GAS,
    "water:total": SensorDeviceClass.WATER,
    "energy:mineelec": SensorDeviceClass.ENERGY,
    "energy:avgelec": SensorDeviceClass.ENERGY,
    "energy:minegas": SensorDeviceClass.GAS,
    "energy:avggas": SensorDeviceClass.GAS,
    "energy:minewater": SensorDeviceClass.WATER,
    "energy:avgwater": SensorDeviceClass.WATER,
    # "온수"/"난방" 유량계에 맞는 HA device_class가 없습니다. 아래 로컬 푸시
    # 방식의 hotwater:total/heat:total 항목과 동일한 상황입니다.
    #
    # No HA device class fits "hot water"/"heating" volume meters, same as
    # their local-push hotwater:total/heat:total counterparts below.
}

DEVICE_UNIT = {
    "light:dcvalue": UnitOfPower.WATT,
    "outlet:cutvalue": UnitOfPower.WATT,
    "outlet:powercons": UnitOfPower.WATT,
    "electric:realtime": UnitOfPower.WATT,
    "electric:total": UnitOfEnergy.KILO_WATT_HOUR,
    "gas:realtime": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "gas:total": UnitOfVolume.CUBIC_METERS,
    "heat:realtime": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "heat:total": UnitOfVolume.CUBIC_METERS,
    "hotwater:realtime": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "hotwater:total": UnitOfVolume.CUBIC_METERS,
    "water:realtime": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "water:total": UnitOfVolume.CUBIC_METERS,
    # 클라우드 에너지 값은 로컬 푸시 *:total 항목과 동일한 계량기를 가리킵니다
    # (RS485 게이트웨이 대신 iparkapp REST API로 조회할 뿐), 단위도 동일합니다.
    #
    # Cloud energy comparison readings report the same physical meters as
    # their local-push *:total counterparts (just via the iparkapp REST API
    # instead of the RS485 gateway), so the units match those above.
    "energy:mineelec": UnitOfEnergy.KILO_WATT_HOUR,
    "energy:avgelec": UnitOfEnergy.KILO_WATT_HOUR,
    "energy:minegas": UnitOfVolume.CUBIC_METERS,
    "energy:avggas": UnitOfVolume.CUBIC_METERS,
    "energy:minewater": UnitOfVolume.CUBIC_METERS,
    "energy:avgwater": UnitOfVolume.CUBIC_METERS,
    "energy:minehwater": UnitOfVolume.CUBIC_METERS,
    "energy:avghwater": UnitOfVolume.CUBIC_METERS,
    "energy:mineheat": UnitOfVolume.CUBIC_METERS,
    "energy:avgheat": UnitOfVolume.CUBIC_METERS,
}

VALUE_CONVERSION = {
    "electric:total": lambda val, _: round(val / 100, 2),
    "gas:total": lambda val, _: round(val / 1000, 2),
    "gas:realtime": lambda val, _: val / 10,
    "heat:total": lambda val, _: round(val / 1000, 2),
    "heat:realtime": lambda val, wp_ver: val if wp_ver == "General" else val / 1000,
    "hotwater:total": lambda val, _: round(val / 1000, 2),
    "hotwater:realtime": lambda val, wp_ver: val if wp_ver == "General" else val / 1000,
    "water:total": lambda val, _: round(val / 1000, 2),
    "water:realtime": lambda val, wp_ver: val if wp_ver == "General" else val / 1000,
    # energy:mine*/avg*는 변환하지 않습니다. iparkapp REST 응답은 이미 스케일이
    # 적용된 값입니다 (예: mine_elec은 kWh 실수로 옵니다) — 로컬 푸시 방식처럼
    # 원시 레지스터 값을 나눠줄 필요가 없습니다.
    #
    # No conversion for energy:mine*/avg* — the iparkapp REST payload already
    # reports these pre-scaled (e.g. mine_elec arrives as a plain kWh float),
    # unlike the raw register values the local push path has to descale.
}

# 누적 계량기 값 — 리셋 전까지는 계속 증가하므로, 값이 떨어지면(계량기
# 리셋) 프런트엔드가 이를 음수 변화가 아니라 새 집계 구간으로 처리해야
# 합니다.
#
# Cumulative meter counters: only increase between resets, so the frontend
# should treat dips (meter rollover) as a new counting period rather than a
# negative delta.
TOTAL_INCREASING_TYPES = {
    "electric:total", "gas:total", "heat:total", "hotwater:total", "water:total",
    "energy:mineelec", "energy:minegas", "energy:minewater",
    "energy:minehwater", "energy:mineheat",
}

# 순간값 — 갱신마다 오르내릴 수 있습니다.
#
# Instantaneous readings: can go up or down between updates.
MEASUREMENT_TYPES = {
    "light:dcvalue", "outlet:cutvalue", "outlet:powercons",
    "electric:realtime", "gas:realtime", "heat:realtime",
    "hotwater:realtime", "water:realtime",
}

# 이웃 평균 — 우리 집 계량기와 같은 '이번 달 누적' 값이지만, 달이 바뀌면
# 0 부터 다시 시작하므로 'total_increasing' 이 아니라 'total' 입니다.
#
# v1.4.11 수정: 이 센서들은 v1.4.10 까지 'measurement' 로 선언되어 있었는데,
# HA 는 device_class 가 energy/gas/water 인 센서에 'measurement' 를 허용하지
# 않습니다. 매 시작마다 다음 경고를 찍으면서 장기 통계를 아예 만들지 않았습니다:
#   "is using state class 'measurement' which is impossible considering
#    device class ('energy')"
#
# Neighbor averages are the same month-to-date accumulation as the household
# meters, but they reset to zero at each month boundary — hence 'total' rather
# than 'total_increasing'.
#
# v1.4.11 fix: these were declared 'measurement' through v1.4.10, which HA
# rejects for energy/gas/water device classes. It logged a warning on every
# start and, more to the point, recorded no long-term statistics for them at
# all — so the neighbor-average sensors had no history to compare against.
TOTAL_TYPES = {
    "energy:avgelec", "energy:avggas", "energy:avgwater",
    "energy:avghwater", "energy:avgheat",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Setup sensor platform."""
    hub: BestinHub = BestinHub.get_hub(hass, entry)
    hub.entity_groups[DOMAIN_SENSOR] = set()

    @callback
    def async_add_sensor(devices=None):
        if devices is None:
            devices = hub.api.get_devices_from_domain(DOMAIN_SENSOR)

        entities = [
            BestinSensor(device, hub) 
            for device in devices 
            if device.unique_id not in hub.entity_groups[DOMAIN_SENSOR]
        ]

        if entities:
            async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, hub.async_signal_new_device(NEW_SENSOR), async_add_sensor
        )
    )
    async_add_sensor()


class BestinSensor(BestinDevice, SensorEntity):
    """Defined the Sensor."""
    TYPE = DOMAIN_SENSOR

    def __init__(self, device, hub) -> None:
        """Initialize the sensor."""
        super().__init__(device, hub)
        # device_type(예: "electric:total", "energy:mineelec")은 이미
        # center.py/iparkapp.py에서 올바르게 만들어진 분류 키이므로,
        # device_id에서 다시 뽑아낼 필요가 없습니다.
        #
        # device_type (e.g. "electric:total", "energy:mineelec") is already
        # the correct classification key straight from center.py/iparkapp.py
        # — no need to re-derive it from device_id.
        self._attr_icon = DEVICE_ICON.get(self._device_info.device_type)

    @property
    def native_value(self):
        """Return the state of the sensor."""
        factor = VALUE_CONVERSION.get(self._device_info.device_type)
        if callable(factor):
            return factor(self._device_info.state, self.hub.wp_version)
        return self._device_info.state

    @property
    def device_class(self):
        """Return the class of the sensor."""
        return DEVICE_CLASS.get(self._device_info.device_type)

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this sensor."""
        return DEVICE_UNIT.get(self._device_info.device_type)

    @property
    def state_class(self):
        """Type of this sensor state."""
        device_type = self._device_info.device_type
        if device_type in TOTAL_INCREASING_TYPES:
            return "total_increasing"
        if device_type in TOTAL_TYPES:
            return "total"
        if device_type in MEASUREMENT_TYPES:
            return "measurement"
        return None
