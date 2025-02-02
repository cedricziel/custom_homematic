"""Generic entity for the HomematicIP Cloud component."""
from __future__ import annotations

import logging
from typing import Any

from hahomematic.entity import CallbackEntity
from hahomematic.hub import BaseHubEntity

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.entity_registry import EntityRegistry

from .control_unit import ControlUnit
from .helper import get_entity_description

_LOGGER = logging.getLogger(__name__)


class HaHomematicGenericEntity(Entity):
    """Representation of the HomematicIP generic entity."""

    def __init__(
        self,
        control_unit: ControlUnit,
        hm_entity,
    ) -> None:
        """Initialize the generic entity."""
        self._cu = control_unit
        self._hm_entity = hm_entity
        if entity_description := get_entity_description(self._hm_entity):
            self.entity_description = entity_description
        # Marker showing that the Hm device hase been removed.
        self.hm_device_removed = False
        _LOGGER.info("Setting up %s", self.name)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._hm_entity.available

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device specific attributes."""
        # Only physical devices should be HA devices.
        info = self._hm_entity.device_info
        return DeviceInfo(
            identifiers=info["identifiers"],
            manufacturer=info["manufacturer"],
            model=info["model"],
            name=info["name"],
            sw_version=info["sw_version"],
            # Link to the homematic ip access point.
            via_device=info["via_device"],
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the generic entity."""
        return self._hm_entity.extra_state_attributes

    @property
    def name(self) -> str:
        """Return the name of the generic entity."""
        return self._hm_entity.name

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._hm_entity.unique_id

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        if isinstance(self._hm_entity, (BaseHubEntity, CallbackEntity)):
            self._hm_entity.register_update_callback(self._async_device_changed)
            self._hm_entity.register_remove_callback(self._async_device_removed)
        self._cu.add_hm_entity(hm_entity=self._hm_entity)
        await self._init_data()

    async def _init_data(self) -> None:
        """Init data. Disable entity if data load fails due to missing device value."""
        if hasattr(self._hm_entity, "load_data"):
            load_state = await self._hm_entity.load_data()
        # if load_state == DATA_LOAD_FAIL and not self.registry_entry.disabled_by:
        #    await self._update_registry_entry(disabled_by=er.DISABLED_INTEGRATION)

    async def _update_registry_entry(self, disabled_by) -> None:
        """Update registry_entry disabled_by."""
        entity_registry: EntityRegistry = await er.async_get_registry(self.hass)
        entity_registry.async_update_entity(self.entity_id, disabled_by=disabled_by)

    @callback
    def _async_device_changed(self, *args, **kwargs) -> None:
        """Handle device state changes."""
        # Don't update disabled entities
        if self.enabled:
            _LOGGER.debug("Event %s", self.name)
            self.async_write_ha_state()
        else:
            _LOGGER.debug(
                "Device Changed Event for %s not fired. Entity is disabled",
                self.name,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Run when hmip device will be removed from hass."""

        # Only go further if the device/entity should be removed from registries
        # due to a removal of the HM device.

        if self.hm_device_removed:
            try:
                self._cu.remove_hm_entity(self)
                await self.async_remove_from_registries()
            except KeyError as err:
                _LOGGER.debug("Error removing HM device from registry: %s", err)

    async def async_remove_from_registries(self) -> None:
        """Remove entity/device from registry."""

        # Remove callback from device.
        self._hm_entity.unregister_update_callback()
        self._hm_entity.unregister_remove_callback()

        if not self.registry_entry:
            return

        if device_id := self.registry_entry.device_id:
            # Remove from device registry.
            device_registry = await dr.async_get_registry(self.hass)
            if device_id in device_registry.devices:
                # This will also remove associated entities from entity registry.
                device_registry.async_remove_device(device_id)
        else:
            # Remove from entity registry.
            # Only relevant for entities that do not belong to a device.
            if entity_id := self.registry_entry.entity_id:
                entity_registry = await er.async_get_registry(self.hass)
                if entity_id in entity_registry.entities:
                    entity_registry.async_remove(entity_id)

    @callback
    def _async_device_removed(self, *args, **kwargs) -> None:
        """Handle hm device removal."""
        # Set marker showing that the Hm device hase been removed.
        self.hm_device_removed = True
        self.hass.async_create_task(self.async_remove(force_remove=True))
