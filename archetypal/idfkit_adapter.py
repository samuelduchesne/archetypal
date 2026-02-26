"""Helper functions for working with idfkit documents.

This module provides utility functions for common operations when extracting
data from idfkit documents for UMI template creation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import idfkit


def get_zone_surfaces(doc: idfkit.Document, zone_name: str) -> list:
    """Get all surfaces belonging to a zone.

    Args:
        doc: idfkit Document object
        zone_name: Name of the zone

    Returns:
        List of surface objects (BuildingSurface:Detailed, etc.)
    """
    surfaces = []
    surface_types = [
        "BuildingSurface:Detailed",
        "Wall:Detailed",
        "RoofCeiling:Detailed",
        "Floor:Detailed",
    ]

    for surf_type in surface_types:
        if surf_type not in doc:
            continue
        for surface in doc[surf_type].values():
            if getattr(surface, "zone_name", None) == zone_name:
                surfaces.append(surface)

    return surfaces


def get_zone_fenestrations(doc: idfkit.Document, zone_name: str) -> list:
    """Get all fenestration surfaces (windows/doors) for a zone.

    Args:
        doc: idfkit Document object
        zone_name: Name of the zone

    Returns:
        List of fenestration surface objects
    """
    zone_surfaces = get_zone_surfaces(doc, zone_name)
    surface_names = {s.name for s in zone_surfaces}

    fenestrations = []
    fenestration_types = [
        "FenestrationSurface:Detailed",
        "Window",
        "Door",
        "GlazedDoor",
    ]

    for fen_type in fenestration_types:
        if fen_type not in doc:
            continue
        for fen in doc[fen_type].values():
            building_surface = getattr(fen, "building_surface_name", None)
            if building_surface in surface_names:
                fenestrations.append(fen)

    return fenestrations


def get_construction_layers(doc: idfkit.Document, construction_name: str) -> list:
    """Get material layers for a construction.

    Args:
        doc: idfkit Document object
        construction_name: Name of the construction

    Returns:
        List of material objects in order from outside to inside
    """
    construction = doc["Construction"].get(construction_name)
    if construction is None:
        return []

    layers = []
    # Construction has layer_1, layer_2, ... layer_10 fields
    for i in range(1, 11):
        layer_name = getattr(construction, f"layer_{i}", None)
        if not layer_name:
            break

        # Find the material in various material types
        material_types = [
            "Material",
            "Material:NoMass",
            "Material:AirGap",
            "WindowMaterial:SimpleGlazingSystem",
            "WindowMaterial:Glazing",
            "WindowMaterial:Gas",
        ]
        for mat_type in material_types:
            if mat_type in doc and layer_name in doc[mat_type]:
                layers.append(doc[mat_type][layer_name])
                break

    return layers


def get_schedule_values(doc: idfkit.Document, schedule_name: str) -> dict:
    """Get schedule definition data.

    Args:
        doc: idfkit Document object
        schedule_name: Name of the schedule

    Returns:
        Dictionary with schedule data
    """
    schedule_types = [
        "Schedule:Compact",
        "Schedule:Year",
        "Schedule:Week:Daily",
        "Schedule:Day:Interval",
        "Schedule:Day:Hourly",
        "Schedule:Day:List",
        "Schedule:Constant",
    ]

    for sched_type in schedule_types:
        if sched_type in doc and schedule_name in doc[sched_type]:
            return doc[sched_type][schedule_name]

    return None
