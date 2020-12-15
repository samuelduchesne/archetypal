from itertools import chain, zip_longest

from eppy.geometry import surface as g_surface
from opyplus.epm.record import Record


def grouper(num, iterable, fillvalue=None):
    """Collect data into fixed-length chunks or blocks."""
    # grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * num
    return zip_longest(fillvalue=fillvalue, *args)


def get_coords(ddtt):
    """Return the coordinates of the surface."""
    _from, steps, *_ = ddtt._table._dev_descriptor.extensible_info
    pts = ddtt[_from:]
    return list(grouper(steps, pts))


def tilt(ddtt):
    """tilt of the surface."""
    coords = get_coords(ddtt)
    return g_surface.tilt(coords)


def get_zone_surfaces(record):
    """Get pointing records that are part of 'Thermal Zones and Surfaces'."""
    sets = {
        key: value
        for (key, value) in record.get_pointing_records().items()
        if value._table._dev_descriptor.group_name == "Thermal Zones and Surfaces"
        and value._table._dev_descriptor.table_ref != "ZoneList"
    }
    return chain(*sets.values())


def area(record):
    """Area of the surface."""
    coords = get_coords(record)
    return g_surface.area(coords)


Record.tilt = property(lambda self: tilt(self))
Record.area = property(lambda self: area(self))
Record.zonesurfaces = property(lambda self: get_zone_surfaces(self))
