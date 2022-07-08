"""Shoebox class."""
import logging
from typing import Optional

from archetypal import IDF
from archetypal.template import ZoneConstructionSet
from archetypal.template.building_template import BuildingTemplate
from archetypal.template.constructions.opaque_construction import OpaqueConstruction
from archetypal.template.constructions.window_construction import WindowConstruction
from archetypal.template.materials import GasMaterial
from archetypal.template.zonedefinition import InternalMass
from eppy.bunch_subclass import BadEPFieldError
from eppy.idf_msequence import Idf_MSequence
from geomeppy.recipes import (
    _has_correct_orientation,
    _is_window,
    window_vertices_given_wall,
)
from validator_collection import checkers, validators

from .hvac_templates import HVACTemplates

log = logging.getLogger(__name__)


class ShoeBox(IDF):
    """Shoebox Model."""

    def __init__(self, *args, azimuth=180, **kwargs):
        """Initialize Shoebox."""
        super(ShoeBox, self).__init__(*args, **kwargs)
        self.azimuth = azimuth  # 0 is north

    @property
    def total_envelope_resistance(self):
        """Get the total envelope resistance [m2-K/W].

        Note:
            The envelope is consisted of surfaces that have an outside boundary
            condition different then `Adiabatic` or `Surface` or that participate in
            the heat exchange with the exterior.

        """
        u_factor_times_area = 0
        gross_area = 0
        for surface in self.getsurfaces():
            # loop over surfaces that have heat exchange
            if surface.Outside_Boundary_Condition.lower() in ["adiabatic", "surface"]:
                continue
            construction = surface.get_referenced_object("Construction_Name")
            surface_construction = OpaqueConstruction.from_epbunch(construction)
            surface_area = surface.area
            gross_area += surface_area

            # for the surface, loop over subsurfaces (aka windows)
            surface_window_area = 0
            window_u_factor = 0
            for subsurface in surface.subsurfaces:
                construction = subsurface.get_referenced_object("Construction_Name")
                window = WindowConstruction.from_epbunch(construction)
                surface_window_area += subsurface.area
                window_u_factor += window.u_factor * subsurface.area

            # calculate the u_factor_times_area
            u_factor_times_area += (
                surface_construction.u_factor * (surface_area - surface_window_area)
                + window_u_factor
            )
        return 1 / (u_factor_times_area / gross_area)

    @property
    def total_envelope_area(self):
        """Get the total gross envelope area including windows [m2].

        Note:
            The envelope is consisted of surfaces that have an outside boundary
            condition different then `Adiabatic` or `Surface` or that participate in
            the heat exchange with the exterior.

        """
        total_area = 0
        for surface in self.getsurfaces():
            if surface.Outside_Boundary_Condition.lower() in ["adiabatic", "surface"]:
                continue
            total_area += surface.area
        return total_area

    @property
    def total_building_volume(self):
        """Get the total building air volume [m3]."""
        import numpy as np
        from scipy.spatial import ConvexHull

        volume = 0
        for zone in self.idfobjects["ZONE"]:
            points = []
            for surface in zone.zonesurfaces:
                if hasattr(surface, "coords"):
                    points.extend(surface.coords)
            points = np.array(points)  # the points as (npoints, ndim)
            volume += ConvexHull(points).volume * float(zone.Multiplier)
        return volume

    @property
    def building_air_thermal_capacitance(self):
        """Get the thermal capacitance of the building air only.

        Notes:
            m3 * kg/m3 * J/kg-K => J/K
        """
        air = GasMaterial("AIR")
        air_capacitance = (
            self.total_building_volume
            * air.density_at_temperature(21 + 273.15)
            * air.specific_heat
        )
        return air_capacitance

    @property
    def thermal_capacitance(self):
        """Get the thermal capacitance of the building air + internal mass objects.

        Notes:
            m3 * kg/m3 * J/kg-K => J/K
        """
        air = GasMaterial("AIR")
        air_capacitance = (
            self.total_building_volume
            * air.density_at_temperature(21 + 273.15)
            * air.specific_heat
        )

        internal_mass_capacitance = 0
        for ep_bunch in self.idfobjects["INTERNALMASS"]:
            internal_mass = OpaqueConstruction.from_epbunch(
                ep_bunch.get_referenced_object("Construction_Name")
            )
            internal_mass_capacitance += (
                float(ep_bunch.Surface_Area)
                * internal_mass.heat_capacity_per_unit_wall_area
            )
        return air_capacitance + internal_mass_capacitance

    @classmethod
    def minimal(cls, **kwargs):
        """Create the minimal viable IDF model.

        BUILDING, GlobalGeometryRules, LOCATION and DESIGNDAY (or RUNPERIOD) are the
        absolute minimal required input objects.

        Args:
            **kwargs: keyword arguments passed to the IDF constructor.

        Returns:
            ShoeBox: The ShoeBox model.
        """
        idf = cls(**kwargs)

        idf.newidfobject("BUILDING", Name=idf.name or "None")
        idf.newidfobject(
            "GLOBALGEOMETRYRULES",
            Starting_Vertex_Position="UpperLeftCorner",
            Vertex_Entry_Direction="CounterClockWise",
            Coordinate_System="World",
        )
        idf.newidfobject(
            "RUNPERIOD",
            Name="Run Period 1",
            Begin_Month=1,
            Begin_Day_of_Month=1,
            End_Month=12,
            End_Day_of_Month=31,
        )
        idf.newidfobject(
            "SIMULATIONCONTROL",
            Do_Zone_Sizing_Calculation="No",
            Do_System_Sizing_Calculation="No",
            Run_Simulation_for_Sizing_Periods="No",
            Do_HVAC_Sizing_Simulation_for_Sizing_Periods="No",
        )
        return idf

    @classmethod
    def from_template(
        cls,
        building_template,
        system=HVACTemplates.SimpleIdealLoadsSystem.name,
        ddy_file=None,
        height=3,
        number_of_stories=1,
        ground_temperature=10,
        wwr_map=None,
        coordinates=None,
        zones_data=None,
        zoning="by_storey",
        **kwargs,
    ):
        """Create Shoebox from a template.

        Args:
            system (str): Name of HVAC system template. Default
                :"SimpleIdealLoadsSystem".
            building_template (BuildingTemplate):
            ddy_file:
            ground_temperature (int or list): The ground temperature in degC. If a
                single numeric value is passed, the value is applied to all months.
                If a list is passed, it must have len == 12.
            zones_data (list of dict): Specify the size and name of zones to create
                with a list of dict. The list of dict should have this form:
                {"name": "Core", "coordinates": [(10, 0), (10, 5), (0, 5), (0, 0)],
                "height": 3, "num_stories": 1, "zoning": "by_storey", "perim_depth":
                3}. See :meth:`geomeppy.idf.IDF.add_block` for more information on the
                attributes of the zone dict.
            zoning (str): The zoning pattern of the zone. Default : "by_storey".

        Returns:
            ShoeBox: A shoebox for this building_template
        """
        idf = cls.minimal(**kwargs)

        assert zoning in [
            "by_storey",
            "core/perim",
        ], f"Expected 'by_storey' or 'core/perim' for attr 'zoning', not {zoning}."

        # Create Core box
        if zones_data is None:
            zones_data = [
                {
                    "name": "Core",
                    "coordinates": coordinates or [(10, 0), (10, 5), (0, 5), (0, 0)],
                    "height": height,
                    "num_stories": number_of_stories,
                    "zoning": zoning,
                    "perim_depth": 3,
                },
            ]
            if zoning == "by_storey":
                # Add second zone if zoning scheme is "by_storey", else 'core/perim'
                # will deal with creating the extra zones.
                zones_data.append(
                    {
                        "name": "Perim",
                        "coordinates": coordinates or [(10, 5), (10, 10), (0, 10), (0, 5)],
                        "height": height,
                        "num_stories": number_of_stories,
                        "zoning": zoning,
                        "perim_depth": 3,
                    }
                )
        for zone_dict in zones_data:
            idf.add_block(**zone_dict)
        # Join adjacent walls
        idf.intersect_match()

        # Todo: split roof and ceiling:

        # Constructions
        idf.set_constructions(building_template.Perimeter.Constructions)

        # Add window construction
        window = building_template.Windows.Construction.to_epbunch(idf)

        # Set wwr
        if wwr_map is None:
            wwr_map = {
                0: 0,
                90: 0,
                180: 0,
                270: 0,
            }  # initialize wwr_map for orientation.
            wwr_map.update({idf.azimuth: building_template.DefaultWindowToWallRatio})
        set_wwr(idf, construction=window.Name, wwr_map=wwr_map, force=True)

        if ddy_file:
            idf.add_sizing_design_day(ddy_file)

        # add ground temperature
        if ground_temperature:
            idf.ground_temperatures = ground_temperature
            idf.newidfobject(
                "Site:GroundTemperature:BuildingSurface".upper(),
                **{
                    f"{month}_Ground_Temperature": temperature
                    for month, temperature in zip(
                        [
                            "January",
                            "February",
                            "March",
                            "April",
                            "May",
                            "June",
                            "July",
                            "August",
                            "September",
                            "October",
                            "November",
                            "December",
                        ],
                        idf.ground_temperatures,
                    )
                },
            )

        for zone in idf.idfobjects["ZONE"]:
            # Calculate zone area
            zone_floor_area = cls.zone_floor_area(zone)

            # infiltration, only `window` surfaces are considered.
            zone_window_area = cls.zone_window_area(zone)
            opening_area_ratio = building_template.Windows.OperableArea

            if is_core(zone):
                # add internal gains
                building_template.Core.Loads.to_epbunch(idf, zone.Name)

                # Heating System; create one for each zone.
                HVACTemplates[system].create_from(zone, building_template.Core)

                # Create InternalMass object, then convert to EpBunch.
                internal_mass = InternalMass(
                    surface_name=f"{zone.Name} InternalMass",
                    construction=building_template.Core.InternalMassConstruction,
                    total_area_exposed_to_zone=zone_floor_area
                    * building_template.Core.InternalMassExposedPerFloorArea,
                )
                if internal_mass.total_area_exposed_to_zone > 0:
                    internal_mass.to_epbunch(idf, zone.Name)
            else:
                # add internal gains
                building_template.Perimeter.Loads.to_epbunch(idf, zone.Name)

                # Heating System; create one for each zone.
                HVACTemplates[system].create_from(zone, building_template.Perimeter)

                # Create InternalMass object, then convert to EpBunch.
                if building_template.Perimeter.InternalMassExposedPerFloorArea > 0:
                    internal_mass = InternalMass(
                        surface_name=f"{zone.Name} InternalMass",
                        construction=building_template.Perimeter.InternalMassConstruction,
                        total_area_exposed_to_zone=zone_floor_area
                        * building_template.Perimeter.InternalMassExposedPerFloorArea,
                    )
                    internal_mass.to_epbunch(idf, zone.Name)

                # infiltration
                building_template.Perimeter.Ventilation.to_epbunch(
                    idf, zone.Name, opening_area=zone_window_area * opening_area_ratio
                )
        return idf

    @classmethod
    def zone_window_area(cls, zone):
        window_area = 0
        for surface in zone.zonesurfaces:
            for sub_surface in surface.subsurfaces:
                if sub_surface.Surface_Type.lower() == "window":
                    window_area += sub_surface.area
        return window_area

    @classmethod
    def zone_floor_area(cls, zone):
        floor_area = 0
        for surface in zone.zonesurfaces:
            if surface.Surface_Type.lower() == "floor":
                floor_area += surface.area
        return floor_area

    @property
    def ground_temperatures(self):
        """Get or set the ground temperatures."""
        return self._ground_temperatures

    @ground_temperatures.setter
    def ground_temperatures(self, value):
        if checkers.is_numeric(value):
            ground_temperatures = [value] * 12
        elif checkers.is_iterable(value):
            ground_temperature = validators.iterable(
                value, minimum_length=12, maximum_length=12
            )
            ground_temperatures = [temp for temp in ground_temperature]
        else:
            raise ValueError(
                "Input error for value 'ground_temperature'. Value must "
                "be numeric or an iterable of length 12."
            )
        self._ground_temperatures = ground_temperatures

    def add_sizing_design_day(self, ddy_file):
        """Read ddy file and copy objects over to self."""
        ddy = IDF(
            ddy_file, as_version="9.2.0", file_version="9.2.0", prep_outputs=False
        )
        for sequence in ddy.idfobjects.values():
            if sequence:
                for obj in sequence:
                    self.addidfobject(obj)
        del ddy

    def set_constructions(self, zone_construction_set: ZoneConstructionSet):
        """Set constructions from ZoneConstructionSet.

        Args:
            zone_construction_set (ZoneConstructionSet):
        """
        for surface in self.getsurfaces():
            if surface.Surface_Type.lower() == "wall":
                if surface.Outside_Boundary_Condition.lower() == "outdoors":
                    surface.Construction_Name = zone_construction_set.Facade.to_epbunch(
                        self
                    ).Name
                    if zone_construction_set.IsFacadeAdiabatic:
                        surface.Outside_Boundary_Condition = "Adiabatic"
                elif surface.Outside_Boundary_Condition.lower() == "ground":
                    surface.Construction_Name = zone_construction_set.Facade.to_epbunch(
                        self
                    ).Name
                    if zone_construction_set.IsFacadeAdiabatic:
                        surface.Outside_Boundary_Condition = "Adiabatic"
                else:
                    surface.Construction_Name = (
                        zone_construction_set.Partition.to_epbunch(self).Name
                    )
                    if zone_construction_set.IsPartitionAdiabatic:
                        surface.Outside_Boundary_Condition = "Adiabatic"
            if surface.Surface_Type.lower() == "floor":
                if surface.Outside_Boundary_Condition.lower() == "ground":
                    surface.Construction_Name = zone_construction_set.Ground.to_epbunch(
                        self
                    ).Name
                    if zone_construction_set.IsGroundAdiabatic:
                        surface.Outside_Boundary_Condition = "Adiabatic"
                else:
                    surface.Construction_Name = zone_construction_set.Slab.to_epbunch(
                        self
                    ).Name
                    if zone_construction_set.IsSlabAdiabatic:
                        surface.Outside_Boundary_Condition = "Adiabatic"
            if surface.Surface_Type.lower() == "roof":
                surface.Construction_Name = zone_construction_set.Roof.to_epbunch(
                    self
                ).Name
                if zone_construction_set.IsRoofAdiabatic:
                    surface.Outside_Boundary_Condition = "Adiabatic"
            if surface.Surface_Type.lower() == "ceiling":
                surface.Construction_Name = zone_construction_set.Slab.to_epbunch(
                    self
                ).Name
                if zone_construction_set.IsSlabAdiabatic:
                    surface.Outside_Boundary_Condition = "Adiabatic"


def set_wwr(
    idf, wwr=0.2, construction=None, force=False, wwr_map=None, orientation=None
):
    # type: (IDF, Optional[float], Optional[str], Optional[bool], Optional[dict], Optional[str]) -> None
    """Set the window to wall ratio on all external walls.

    :param idf: The IDF to edit.
    :param wwr: The window to wall ratio.
    :param construction: Name of a window construction.
    :param force: True to remove all subsurfaces before setting the WWR.
    :param wwr_map: Mapping from wall orientation (azimuth) to WWR, e.g. {180: 0.25, 90: 0.2}.
    :param orientation: One of "north", "east", "south", "west". Walls within 45 degrees will be affected.

    Todo: replace with original package method when PR is accepted.
    """
    try:
        ggr = idf.idfobjects["GLOBALGEOMETRYRULES"][0]  # type: Optional[Idf_MSequence]
    except IndexError:
        ggr = None

    # check orientation
    orientations = {
        "north": 0.0,
        "east": 90.0,
        "south": 180.0,
        "west": 270.0,
        None: None,
    }
    degrees = orientations.get(orientation, None)
    external_walls = filter(
        lambda x: x.Outside_Boundary_Condition.lower() == "outdoors",
        idf.getsurfaces("wall"),
    )
    external_walls = filter(
        lambda x: _has_correct_orientation(x, degrees), external_walls
    )
    subsurfaces = idf.getsubsurfaces()
    base_wwr = wwr
    for wall in external_walls:
        # get any subsurfaces on the wall
        wall_subsurfaces = list(
            filter(lambda x: x.Building_Surface_Name == wall.Name, subsurfaces)
        )
        if not all(_is_window(wss) for wss in wall_subsurfaces) and not force:
            raise ValueError(
                'Not all subsurfaces on wall "{name}" are windows. '
                "Use `force=True` to replace all subsurfaces.".format(name=wall.Name)
            )

        if wall_subsurfaces and not construction:
            constructions = list(
                {wss.Construction_Name for wss in wall_subsurfaces if _is_window(wss)}
            )
            if len(constructions) > 1:
                raise ValueError(
                    'Not all subsurfaces on wall "{name}" have the same construction'.format(
                        name=wall.Name
                    )
                )
            construction = constructions[0]
        # remove all subsurfaces
        for ss in wall_subsurfaces:
            idf.removeidfobject(ss)
        wwr = (wwr_map or {}).get(wall.azimuth, base_wwr)
        if not wwr:
            continue
        coords = window_vertices_given_wall(wall, wwr)
        window = idf.newidfobject(
            "FENESTRATIONSURFACE:DETAILED",
            Name="%s window" % wall.Name,
            Surface_Type="Window",
            Construction_Name=construction or "",
            Building_Surface_Name=wall.Name,
            View_Factor_to_Ground="autocalculate",  # from the surface angle
        )
        window.setcoords(coords, ggr)


def is_core(zone_ep):
    # if all surfaces don't have boundary condition == "Outdoors"
    iscore = True
    for s in zone_ep.zonesurfaces:
        try:
            if (abs(int(s.tilt)) < 180) & (abs(int(s.tilt)) > 0):
                obc = s.Outside_Boundary_Condition.lower()
                if obc in ["outdoors", "ground"]:
                    iscore = False
                    break
        except BadEPFieldError:
            pass  # pass surfaces that don't have an OBC,
            # eg. InternalMass
    return iscore
