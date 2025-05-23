import logging
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.components.persistent_notification import create, dismiss
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from .mqtt import MQTT
from .ramses_esp import RamsesESP
from .payloads import Code22f1
from .const import (
    DOMAIN,
    CONF_GATEWAY_ID,
    CONF_REMOTE_ID,
    CONF_FAN_ID,
    CONF_CO2_ID,
    CONF_MQTT_TOPIC,
)

# TODO:
# * self.ramses_esp.setup should also run on 1st install of integration
# * Add USB support for Ramses ESP
# * Add mqtt_publish retry if no response from remote
# * Create devices with info from 10E0
# * Start timer on timed fan modes (22F3)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    config = hass.data[DOMAIN][entry.entry_id]
    gateway_id = config.get(CONF_GATEWAY_ID)
    remote_id = config.get(CONF_REMOTE_ID)
    fan_id = config.get(CONF_FAN_ID)
    co2_id = config.get(CONF_CO2_ID)
    mqtt_topic = config.get(CONF_MQTT_TOPIC)
    async_add_entities([OrconFan(hass, gateway_id, remote_id, fan_id, co2_id, mqtt_topic)])


class OrconFan(FanEntity):
    _attr_preset_modes = Code22f1.presets()
    _attr_supported_features = FanEntityFeature.PRESET_MODE

    def __init__(self, hass, gateway_id, remote_id, fan_id, co2_id, mqtt_topic):
        self.hass = hass
        self._attr_name = "Orcon MVS Ventilation"
        self._attr_unique_id = f"orcon_mvs_{fan_id}"
        self._gateway_id = gateway_id
        self._remote_id = remote_id
        self._fan_id = fan_id
        self._co2_id = co2_id
        self._mqtt_topic = mqtt_topic
        self._attr_preset_mode = "Auto"
        self._co2 = None
        self._vent_demand = None
        self._relative_humidity = None
        self._fault_notified = False

    @property
    def extra_state_attributes(self):
        return {
            "co2": self._co2,
            "vent_demand": self._vent_demand,
            "relative_humidity": self._relative_humidity,
        }

    async def async_added_to_hass(self):
        sub_topic = f"{self._mqtt_topic}/{self._gateway_id}/rx"
        pub_topic = f"{self._mqtt_topic}/{self._gateway_id}/tx"
        mqtt = MQTT(self.hass, sub_topic, pub_topic)
        self.ramses_esp = RamsesESP(
            hass=self.hass,
            mqtt=mqtt,
            gateway_id=self._gateway_id,
            remote_id=self._remote_id,
            fan_id=self._fan_id,
            co2_id=self._co2_id,
            callbacks={
                "1298": self.co2_callback,
                "12A0": self.relative_humidity_callback,
                "31D9": self.fan_state_callback,
                "31E0": self.vent_demand_callback,
            },
        )
        mqtt.handle_message = self.ramses_esp.handle_mqtt_message
        await mqtt.setup()
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self.ramses_esp.setup)

    async def async_set_preset_mode(self, preset_mode: str):
        await self.ramses_esp.set_preset_mode(preset_mode)

    async def async_will_remove_from_hass(self):
        if hasattr(self, "_unsub_interval"):
            self._unsub_interval()

    def fan_state_callback(self, status):
        """Update fan state"""
        _LOGGER.info(f"Fan mode: {self._attr_preset_mode}")
        self._attr_preset_mode = status["fan_mode"]
        self.async_write_ha_state()
        if status["has_fault"]:
            if not self._fault_notified:
                _LOGGER.warning("Fan reported a fault")
                create(
                    self.hass, "Orcon MVS15 ventilator reported a fault", title="Orcon MVS15 error", notification_id="FAN_FAULT"
                )
                self._fault_notified = True
        else:
            if self._fault_notified:
                _LOGGER.info("Fan fault cleared")
                dismiss(self.hass, "FAN_FAULT")
                self._fault_notified = False

    def co2_callback(self, status):
        """Update CO2 sensor + attribute"""
        self._co2 = status["level"]
        if sensor := self.hass.data[DOMAIN].get("co2_sensor"):
            sensor.update_state(self._co2)
        self.async_write_ha_state()
        _LOGGER.info(f"CO2: {status['level']} ppm")

    def vent_demand_callback(self, status):
        """Update Vent demand attribute"""
        self._vent_demand = status["percentage"]
        self.async_write_ha_state()
        _LOGGER.info(f"Vent demand: {self._vent_demand}%")

    def relative_humidity_callback(self, status):
        """Update relative humidity attribute"""
        self._relative_humidity = status["level"]
        if sensor := self.hass.data[DOMAIN].get("humidity_sensor"):
            sensor.update_state(self._relative_humidity)
        self.async_write_ha_state()
        _LOGGER.info(f"Relative humidty: {self._relative_humidity}%")
