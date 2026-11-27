"""Small lookups in Home Assistant's area, device, entity and label registries.

These mirror the template functions the scripts use (area_entities, area_id,
label_entities), so the integration finds the same things the scripts did.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    label_registry as lr,
)


def area_of(hass: HomeAssistant, entity_id: str) -> str | None:
    """The area of an entity, or of its device when the entity has none."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None:
        return None
    if entry.area_id:
        return entry.area_id
    if entry.device_id and (device := dr.async_get(hass).async_get(entry.device_id)):
        return device.area_id
    return None


def area_entities(hass: HomeAssistant, area_id: str) -> list[str]:
    """Every entity in an area, including entities that inherit their device's."""
    ent_reg = er.async_get(hass)
    ids = {e.entity_id for e in er.async_entries_for_area(ent_reg, area_id)}
    for device in dr.async_entries_for_area(dr.async_get(hass), area_id):
        for entry in er.async_entries_for_device(ent_reg, device.id):
            if entry.area_id is None:
                ids.add(entry.entity_id)
    return sorted(ids)


def area_name(hass: HomeAssistant, area_id: str) -> str:
    """The area's display name, or '' when it does not exist."""
    area = ar.async_get(hass).async_get_area(area_id)
    return area.name if area else ""


def resolve_area(hass: HomeAssistant, value: str | None) -> str | None:
    """Turn an area id or an area name (as Bermuda reports it) into an area id."""
    if not value:
        return None
    reg = ar.async_get(hass)
    if area := reg.async_get_area(value):
        return area.id
    if area := reg.async_get_area_by_name(value):
        return area.id
    return None


def label_entities(hass: HomeAssistant, label: str) -> set[str]:
    """Entities with a label (by name or id), directly or through their device."""
    label_reg = lr.async_get(hass)
    found = label_reg.async_get_label(label) or label_reg.async_get_label_by_name(label)
    if found is None:
        return set()
    ent_reg = er.async_get(hass)
    ids = {e.entity_id for e in er.async_entries_for_label(ent_reg, found.label_id)}
    for device in dr.async_entries_for_label(dr.async_get(hass), found.label_id):
        ids.update(e.entity_id for e in er.async_entries_for_device(ent_reg, device.id))
    return ids


def device_of(hass: HomeAssistant, entity_id: str) -> str | None:
    """The device id of an entity."""
    entry = er.async_get(hass).async_get(entity_id)
    return entry.device_id if entry else None


def device_entities(hass: HomeAssistant, device_id: str) -> list[str]:
    """Every entity of a device."""
    return [
        e.entity_id
        for e in er.async_entries_for_device(er.async_get(hass), device_id)
    ]
