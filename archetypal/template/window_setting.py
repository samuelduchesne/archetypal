"""archetypal WindowSettings."""

import collections
import logging as lg
from copy import copy
from functools import reduce
from typing import TYPE_CHECKING, ClassVar

from validator_collection import checkers, validators

from archetypal.template.constructions.window_construction import (
    ShadingType,
    WindowConstruction,
    WindowType,
)
from archetypal.template.schedule import UmiSchedule
from archetypal.template.umi_base import UmiBase
from archetypal.utils import log, timeit

if TYPE_CHECKING:
    import idfkit


class WindowSetting(UmiBase):
    """Defines the various window-related properties of a :class:`Zone`.

    Control natural ventilation, shading and airflow networks and more using this
    class. This class serves the same role as the ZoneInformation>Windows tab in the
    UMI TemplateEditor.

    .. image:: ../images/template/zoneinfo-windows.png

    Hint:
        The WindowSetting class implements two constructors that are tailored to
        the eppy_ scripting language:

        - :func:`from_construction` and
        - :func:`from_surface`.

    .. _eppy : https://eppy.readthedocs.io/en/latest/
    """

    _CREATED_OBJECTS: ClassVar[list["WindowSetting"]] = []

    __slots__ = (
        "_operable_area",
        "_afn_discharge_c",
        "_afn_temp_setpoint",
        "_shading_system_setpoint",
        "_shading_system_transmittance",
        "_zone_mixing_availability_schedule",
        "_shading_system_availability_schedule",
        "_construction",
        "_afn_window_availability",
        "_is_shading_system_on",
        "_is_virtual_partition",
        "_is_zone_mixing_on",
        "_shading_system_type",
        "_type",
        "_zone_mixing_delta_temperature",
        "_zone_mixing_flow_rate",
        "_area",
    )

    def __init__(
        self,
        Name,
        Construction=None,
        OperableArea=0.8,
        AfnWindowAvailability=None,
        AfnDischargeC=0.65,
        AfnTempSetpoint=20,
        IsVirtualPartition=False,
        IsShadingSystemOn=False,
        ShadingSystemAvailabilitySchedule=None,
        ShadingSystemSetpoint=180,
        ShadingSystemTransmittance=0.5,
        ShadingSystemType=ShadingType.ExteriorShade,
        Type=WindowType.External,
        IsZoneMixingOn=False,
        ZoneMixingAvailabilitySchedule=None,
        ZoneMixingDeltaTemperature=2,
        ZoneMixingFlowRate=0.001,
        area=1,
        **kwargs,
    ):
        """Initialize a WindowSetting using default values.

        Args:
            Construction (WindowConstruction): The window construction.
            OperableArea (float): The operable window area as a ratio of total
                window area. eg. 0.8 := 80% of the windows area is operable.
            AfnWindowAvailability (UmiSchedule): The Airflow Network availability
                schedule.
            AfnDischargeC (float): Airflow Network Discharge Coefficient.
                Default = 0.65.
            AfnTempSetpoint (float): Airflow Network Temperature Setpoint.
                Default = 20 degreeC.
            IsVirtualPartition (bool): Virtual Partition.
            IsShadingSystemOn (bool): Shading is used. Default is False.
            ShadingSystemAvailabilitySchedule (UmiSchedule): Shading system
                availability schedule.
            ShadingSystemSetpoint (float): Shading system setpoint in units of
                W/m2. Default = 180 W/m2.
            ShadingSystemTransmittance (float): Shading system transmittance.
                Default = 0.5.
            ShadingSystemType (int): Shading System Type. 0 = ExteriorShade, 1 =
                InteriorShade.
            Type (int):
            IsZoneMixingOn (bool): Zone mixing.
            ZoneMixingAvailabilitySchedule (UmiSchedule): Zone mixing
                availability schedule.
            ZoneMixingDeltaTemperature (float): Zone mixing delta
            ZoneMixingFlowRate (float): Zone mixing flow rate in units of m3/m2.
                Default = 0.001 m3/m2.
            **kwargs: other keywords passed to the constructor.
        """
        super().__init__(Name, **kwargs)

        self.ShadingSystemAvailabilitySchedule = ShadingSystemAvailabilitySchedule
        self.Construction = Construction
        self.AfnWindowAvailability = AfnWindowAvailability
        self.AfnDischargeC = AfnDischargeC
        self.AfnTempSetpoint = AfnTempSetpoint
        self.IsShadingSystemOn = IsShadingSystemOn
        self.IsVirtualPartition = IsVirtualPartition
        self.IsZoneMixingOn = IsZoneMixingOn
        self.OperableArea = OperableArea
        self.ShadingSystemSetpoint = ShadingSystemSetpoint
        self.ShadingSystemTransmittance = ShadingSystemTransmittance
        self.ShadingSystemType = ShadingSystemType
        self.Type = Type
        self.ZoneMixingDeltaTemperature = ZoneMixingDeltaTemperature
        self.ZoneMixingFlowRate = ZoneMixingFlowRate
        self.ZoneMixingAvailabilitySchedule = ZoneMixingAvailabilitySchedule

        self.area = area

        # Only at the end append self to _CREATED_OBJECTS
        self._CREATED_OBJECTS.append(self)

    @property
    def area(self):
        """Get or set the area of the zone associated to this object [m²]."""
        return self._area

    @area.setter
    def area(self, value):
        self._area = validators.float(value, minimum=0)

    @property
    def OperableArea(self):
        """Get or set the operable area ratio [-]."""
        return self._operable_area

    @OperableArea.setter
    def OperableArea(self, value):
        self._operable_area = validators.float(value, minimum=0, maximum=1)

    @property
    def AfnDischargeC(self):
        """Get or set the air flow network discarge coefficient."""
        return self._afn_discharge_c

    @AfnDischargeC.setter
    def AfnDischargeC(self, value):
        self._afn_discharge_c = validators.float(value, minimum=0, maximum=1)

    @property
    def AfnTempSetpoint(self):
        """Get or set the air flow network setpoint temperature [degC]."""
        return self._afn_temp_setpoint

    @AfnTempSetpoint.setter
    def AfnTempSetpoint(self, value):
        self._afn_temp_setpoint = validators.float(value, minimum=-100, maximum=100)

    @property
    def AfnWindowAvailability(self):
        """Get or set the air flow network window availability schedule."""
        return self._afn_window_availability

    @AfnWindowAvailability.setter
    def AfnWindowAvailability(self, value):
        if value is not None:
            assert isinstance(value, UmiSchedule), (
                f"Input error with value {value}. AfnWindowAvailability must " f"be an UmiSchedule, not a {type(value)}"
            )
        self._afn_window_availability = value

    @property
    def ShadingSystemType(self):
        """Get or set the shading system type [enum]."""
        return self._shading_system_type

    @ShadingSystemType.setter
    def ShadingSystemType(self, value):
        if checkers.is_string(value):
            assert ShadingType[value], (
                f"Input value error for '{value}'. " f"Expected one of {tuple(a for a in ShadingType)}"
            )
            self._shading_system_type = ShadingType[value]
        elif checkers.is_numeric(value):
            assert ShadingType(value), (
                f"Input value error for '{value}'. " f"Expected one of {tuple(a for a in ShadingType)}"
            )
            self._shading_system_type = ShadingType(value)
        elif isinstance(value, ShadingType):
            self._shading_system_type = value

    @property
    def ShadingSystemSetpoint(self):
        """Get or set the shading system setpoint [W/m2]."""
        return self._shading_system_setpoint

    @ShadingSystemSetpoint.setter
    def ShadingSystemSetpoint(self, value):
        self._shading_system_setpoint = validators.float(value, minimum=0)

    @property
    def ShadingSystemTransmittance(self):
        """Get or set the shading system transmittance [-]."""
        return self._shading_system_transmittance

    @ShadingSystemTransmittance.setter
    def ShadingSystemTransmittance(self, value):
        self._shading_system_transmittance = validators.float(value, minimum=0, maximum=1)

    @property
    def ShadingSystemAvailabilitySchedule(self):
        """Get or set the shading system availability schedule."""
        return self._shading_system_availability_schedule

    @ShadingSystemAvailabilitySchedule.setter
    def ShadingSystemAvailabilitySchedule(self, value):
        if value is not None:
            assert isinstance(value, UmiSchedule), (
                f"Input error with value {value}. ZoneMixingAvailabilitySchedule must "
                f"be an UmiSchedule, not a {type(value)}"
            )
        self._shading_system_availability_schedule = value

    @property
    def IsShadingSystemOn(self):
        """Get or set the use of the shading system."""
        return self._is_shading_system_on

    @IsShadingSystemOn.setter
    def IsShadingSystemOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsShadingSystemOn must " f"be a boolean, not a {type(value)}"
        )
        self._is_shading_system_on = value

    @property
    def ZoneMixingAvailabilitySchedule(self):
        """Get or set the zone mixing availability schedule."""
        return self._zone_mixing_availability_schedule

    @ZoneMixingAvailabilitySchedule.setter
    def ZoneMixingAvailabilitySchedule(self, value):
        if value is not None:
            assert isinstance(value, UmiSchedule), (
                f"Input error with value {value}. ZoneMixingAvailabilitySchedule must "
                f"be an UmiSchedule, not a {type(value)}"
            )
        self._zone_mixing_availability_schedule = value

    @property
    def ZoneMixingDeltaTemperature(self):
        """Get or set the zone mixing delta temperature."""
        return self._zone_mixing_delta_temperature

    @ZoneMixingDeltaTemperature.setter
    def ZoneMixingDeltaTemperature(self, value):
        self._zone_mixing_delta_temperature = validators.float(value, minimum=0)

    @property
    def Construction(self):
        """Get or set the window construction."""
        return self._construction

    @Construction.setter
    def Construction(self, value):
        if value is not None:
            assert isinstance(value, WindowConstruction), (
                f"Input error with value {value}. Construction must " f"be an WindowConstruction, not a {type(value)}"
            )
        self._construction = value

    @property
    def IsVirtualPartition(self):
        """Get or set the state of the virtual partition."""
        return self._is_virtual_partition

    @IsVirtualPartition.setter
    def IsVirtualPartition(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsVirtualPartition must " f"be a boolean, not a {type(value)}"
        )
        self._is_virtual_partition = value

    @property
    def IsZoneMixingOn(self):
        """Get or set mixing in zone."""
        return self._is_zone_mixing_on

    @IsZoneMixingOn.setter
    def IsZoneMixingOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsZoneMixingOn must " f"be a boolean, not a {type(value)}"
        )
        self._is_zone_mixing_on = value

    @property
    def ZoneMixingFlowRate(self):
        """Get or set the zone mixing flow rate [m3/s]."""
        return self._zone_mixing_flow_rate

    @ZoneMixingFlowRate.setter
    def ZoneMixingFlowRate(self, value):
        self._zone_mixing_flow_rate = validators.float(value, minimum=0)

    @property
    def Type(self):
        """Get or set the window type [enum]."""
        return self._type

    @Type.setter
    def Type(self, value):
        if checkers.is_string(value):
            assert WindowType[value], (
                f"Input value error for '{value}'. " f"Expected one of {tuple(a for a in WindowType)}"
            )
            self._type = WindowType[value]
        elif checkers.is_numeric(value):
            assert WindowType(value), (
                f"Input value error for '{value}'. " f"Expected one of {tuple(a for a in WindowType)}"
            )
            self._type = WindowType(value)
        elif isinstance(value, WindowType):
            self._type = value

    def __add__(self, other):
        """Combine self and other."""
        return self.combine(other)

    def __repr__(self):
        """Return a representation of self."""
        return super().__repr__()

    def __str__(self):
        """Return string representation."""
        return repr(self)

    def __hash__(self):
        """Return the hash value of self."""
        return hash(self.id)

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, WindowSetting):
            return NotImplemented
        else:
            return all(
                [
                    self.Construction == other.Construction,
                    self.OperableArea == other.OperableArea,
                    self.AfnWindowAvailability == other.AfnWindowAvailability,
                    self.AfnDischargeC == other.AfnDischargeC,
                    self.AfnTempSetpoint == other.AfnTempSetpoint,
                    self.IsVirtualPartition == other.IsVirtualPartition,
                    self.IsShadingSystemOn == other.IsShadingSystemOn,
                    self.ShadingSystemAvailabilitySchedule == other.ShadingSystemAvailabilitySchedule,
                    self.ShadingSystemSetpoint == other.ShadingSystemSetpoint,
                    self.ShadingSystemTransmittance == other.ShadingSystemTransmittance,
                    self.ShadingSystemType == other.ShadingSystemType,
                    self.Type == other.Type,
                    self.IsZoneMixingOn == other.IsZoneMixingOn,
                    self.ZoneMixingAvailabilitySchedule == other.ZoneMixingAvailabilitySchedule,
                    self.ZoneMixingDeltaTemperature == other.ZoneMixingDeltaTemperature,
                    self.ZoneMixingFlowRate == other.ZoneMixingFlowRate,
                ]
            )

    @classmethod
    def generic(cls, Name):
        """Initialize a generic window with SHGC=0.704, UFactor=2.703, Tvis=0.786.

        Args:
            Name (str): Name of the WindowSetting
        """
        construction = WindowConstruction.from_shgc(
            "SimpleWindow:SINGLE PANE HW WINDOW",
            u_factor=2.703,
            solar_heat_gain_coefficient=0.704,
            visible_transmittance=0.786,
        )
        return WindowSetting(Name, Construction=construction)

    @classmethod
    def from_construction(cls, Construction, doc: "idfkit.Document" = None, **kwargs):
        """Make a :class:`WindowSetting` directly from a Construction_ object.

        .. _Construction : https://bigladdersoftware.com/epx/docs/8-9/input-output-reference/group-surface-construction-elements.html#construction-000

        Args:
            Construction: The construction idfkit object or name.
            doc (idfkit.Document): The idfkit Document for lookups.
            **kwargs: Other keywords passed to the constructor.

        Returns:
            (WindowSetting): The window setting object.
        """
        constr_name = Construction.name if hasattr(Construction, "name") else str(Construction)
        name = kwargs.pop("Name", constr_name + "_Window")
        construction = WindowConstruction.from_idf_object(Construction, doc=doc, **kwargs)
        AfnWindowAvailability = UmiSchedule.constant_schedule()
        ShadingSystemAvailabilitySchedule = UmiSchedule.constant_schedule()
        ZoneMixingAvailabilitySchedule = UmiSchedule.constant_schedule()
        return cls(
            Name=name,
            Construction=construction,
            AfnWindowAvailability=AfnWindowAvailability,
            ShadingSystemAvailabilitySchedule=ShadingSystemAvailabilitySchedule,
            ZoneMixingAvailabilitySchedule=ZoneMixingAvailabilitySchedule,
            **kwargs,
        )

    @classmethod
    def from_surface(cls, surface, doc: "idfkit.Document" = None, **kwargs):
        """Build a WindowSetting object from an idfkit fenestration surface object.

        This constructor will detect common window constructions and
        shading devices.

        Args:
            surface: The FenestrationSurface:Detailed or Window idfkit object.
            doc (idfkit.Document): The idfkit Document for lookups.

        Returns:
            (WindowSetting): The window setting object.
        """
        surf_type = surface.type_name.upper() if hasattr(surface, "type_name") else ""

        if surf_type == "FENESTRATIONSURFACE:DETAILED":
            surface_type = getattr(surface, "surface_type", "").lower()
            if surface_type != "window":
                return  # Other surface types (Doors, GlassDoors, etc.) are ignored.
            construction_name = getattr(surface, "construction_name", "")
            construction = doc["Construction"].get(construction_name) if doc else None
            if construction:
                construction = WindowConstruction.from_idf_object(construction, doc=doc)
            else:
                return None
            # Look for shading control
            shading_control_name = getattr(surface, "shading_control_name", "")
            shading_control = None
            if shading_control_name and doc and "WindowShadingControl" in doc:
                shading_control = doc["WindowShadingControl"].get(shading_control_name)
        elif surf_type == "WINDOW":
            construction_name = getattr(surface, "construction_name", "")
            construction = doc["Construction"].get(construction_name) if doc else None
            if construction:
                construction = WindowConstruction.from_idf_object(construction, doc=doc)
            else:
                return None
            # Find WindowShadingControl that references this window
            shading_control = None
            surf_name = getattr(surface, "name", "")
            if doc and "WindowShadingControl" in doc:
                for ctrl in doc["WindowShadingControl"].values():
                    for i in range(1, 10):
                        field = f"fenestration_surface_{i}_name"
                        if getattr(ctrl, field, "") == surf_name:
                            shading_control = ctrl
                            break
                    if shading_control:
                        break
        elif surf_type == "DOOR":
            return  # Simply skip doors.
        else:
            return None

        attr = {}
        if shading_control:
            # a WindowProperty:ShadingControl_ object can be attached to
            # this window
            attr["IsShadingSystemOn"] = True
            setpoint = getattr(shading_control, "setpoint", "")
            if setpoint != "":
                attr["ShadingSystemSetpoint"] = float(setpoint)
            # get shading transmittance
            shade_mat_name = getattr(shading_control, "shading_device_material_name", "")
            if shade_mat_name and doc:
                for mat_type in ["WindowMaterial:Shade", "WindowMaterial:Blind", "WindowMaterial:Screen"]:
                    if mat_type in doc and shade_mat_name in doc[mat_type]:
                        shade_mat = doc[mat_type][shade_mat_name]
                        attr["ShadingSystemTransmittance"] = getattr(shade_mat, "visible_transmittance", 0.5)
                        break
            # get shading control schedule
            is_scheduled = getattr(shading_control, "shading_control_is_scheduled", "").upper()
            if is_scheduled == "YES":
                sched_name = getattr(shading_control, "schedule_name", "")
                sched_obj = doc.get_schedule(sched_name) if doc and sched_name else None
                if sched_obj:
                    attr["ShadingSystemAvailabilitySchedule"] = UmiSchedule.from_idf_object(sched_obj, doc=doc)
                else:
                    attr["ShadingSystemAvailabilitySchedule"] = UmiSchedule.constant_schedule()
            else:
                # Determine which behavior of control
                shade_ctrl_type = getattr(shading_control, "shading_control_type", "")
                if shade_ctrl_type.lower() == "alwaysoff":
                    attr["ShadingSystemAvailabilitySchedule"] = UmiSchedule.constant_schedule(value=0, name="AlwaysOff")
                elif shade_ctrl_type.lower() == "alwayson":
                    attr["ShadingSystemAvailabilitySchedule"] = UmiSchedule.constant_schedule()
                else:
                    surf_name = getattr(surface, "name", "unknown")
                    log(
                        f'Window "{surf_name}" uses a window control type that '
                        f'is not supported: "{shade_ctrl_type}". Reverting to "AlwaysOn"',
                        lg.WARN,
                    )
                    attr["ShadingSystemAvailabilitySchedule"] = UmiSchedule.constant_schedule()
            # get shading type
            shading_type = getattr(shading_control, "shading_type", "")
            if shading_type:
                mapping = {
                    "InteriorShade": ShadingType(1),
                    "ExteriorShade": ShadingType(0),
                    "ExteriorScreen": ShadingType(0),
                    "InteriorBlind": ShadingType(1),
                    "ExteriorBlind": ShadingType(0),
                    "BetweenGlassShade": ShadingType(0),
                    "BetweenGlassBlind": ShadingType(0),
                    "SwitchableGlazing": ShadingType(0),
                }
                attr["ShadingSystemType"] = mapping.get(shading_type, ShadingType(0))
        else:
            # Set default schedules
            attr["ShadingSystemAvailabilitySchedule"] = UmiSchedule.constant_schedule()

        # get airflow network - look for AirflowNetwork:MultiZone:Surface
        afn = None
        surf_name = getattr(surface, "name", "")
        if doc and "AirflowNetwork:MultiZone:Surface" in doc:
            for obj in doc["AirflowNetwork:MultiZone:Surface"].values():
                if getattr(obj, "surface_name", "") == surf_name:
                    afn = obj
                    break

        if afn:
            attr["OperableArea"] = getattr(afn, "windowdoor_opening_factor_or_crack_factor", 0.8)
            leak_name = getattr(afn, "leakage_component_name", "")
            leak = None
            # Find the leakage component
            for leak_type in ["AirflowNetwork:MultiZone:Surface:EffectiveLeakageArea",
                             "AirflowNetwork:MultiZone:Component:HorizontalOpening",
                             "AirflowNetwork:MultiZone:Surface:Crack",
                             "AirflowNetwork:MultiZone:Component:DetailedOpening"]:
                if doc and leak_type in doc and leak_name in doc[leak_type]:
                    leak = doc[leak_type][leak_name]
                    break

            sched_name = getattr(afn, "venting_availability_schedule_name", "")
            if sched_name:
                sched_obj = doc.get_schedule(sched_name) if doc else None
                if sched_obj:
                    attr["AfnWindowAvailability"] = UmiSchedule.from_idf_object(sched_obj, doc=doc)
                else:
                    attr["AfnWindowAvailability"] = UmiSchedule.constant_schedule()
            else:
                attr["AfnWindowAvailability"] = UmiSchedule.constant_schedule()

            if leak:
                leak_type = leak.type_name.upper() if hasattr(leak, "type_name") else ""
                if leak_type == "AIRFLOWNETWORK:MULTIZONE:SURFACE:EFFECTIVELEAKAGEAREA":
                    attr["AfnDischargeC"] = getattr(leak, "discharge_coefficient", 0.65)
                else:
                    log(
                        f'"{leak_type}" is not fully supported. Reverting to defaults for object "{cls.mro()[0].__name__}"',
                        lg.WARNING,
                    )
        else:
            attr["AfnWindowAvailability"] = UmiSchedule.constant_schedule(value=0, Name="AlwaysOff")

        # Zone Mixing is always off
        attr["ZoneMixingAvailabilitySchedule"] = UmiSchedule.constant_schedule(value=0, Name="AlwaysOff")
        DataSource = kwargs.pop("DataSource", "")
        Category = kwargs.pop("Category", "")
        surf_name = getattr(surface, "name", "Window")
        w = cls(
            Name=surf_name,
            Construction=construction,
            Category=Category,
            DataSource=DataSource,
            **attr,
            **kwargs,
        )
        return w

    @classmethod
    @timeit
    def from_zone(cls, zone, doc: "idfkit.Document" = None, **kwargs):
        """Iterate over the zone subsurfaces and create a window object.

        If more than one window is created, use reduce to combine them together.

        Args:
            zone (ZoneDefinition): The Zone object from which the WindowSetting is
                created.
            doc (idfkit.Document): The idfkit Document for lookups.

        Returns:
            WindowSetting: The WindowSetting object for this zone.
        """
        from archetypal.idfkit_adapter import get_zone_fenestrations

        window_sets = []

        if doc is not None:
            # Get fenestration surfaces for this zone
            fenestrations = get_zone_fenestrations(doc, zone.Name)
            for subsurf in fenestrations:
                # For each subsurface, create a WindowSetting object
                ws = cls.from_surface(subsurf, doc=doc, **kwargs)
                if ws is not None:
                    window_sets.append(ws)

        if window_sets:
            # if one or more window has been created, reduce. Using reduce on
            # a len==1 list, will simply return the object.
            window_sets = [ws for ws in window_sets if ws is not None]
            if window_sets:
                return reduce(WindowSetting.combine, window_sets)
        # no window found, probably a core zone, return None.
        return None

    def combine(self, other, weights=None, allow_duplicates=False):
        """Append other to self. Return self + other as a new object.

        Args:
            other (WindowSetting): The other OpaqueMaterial object
            weights (list-like, optional): A list-like object of len 2. If None,
                equal weights are used.

        Returns:
            WindowSetting: A new combined object made of self + other.
        """
        # Check if other is None. Simply return self
        if not other:
            return self

        if not self:
            return other

        if not isinstance(other, self.__class__):
            msg = f"Cannot combine {self.__class__.__name__} with {other.__class__.__name__}"
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        if not weights:
            log(f'using 1 as weighting factor in "{self.__class__.__name__}" ' "combine.")
            weights = [1.0, 1.0]
        meta = self._get_predecessors_meta(other)
        new_attr = {
            "Construction": WindowConstruction.combine(self.Construction, other.Construction, weights),
            "AfnDischargeC": self.float_mean(other, "AfnDischargeC", weights),
            "AfnTempSetpoint": self.float_mean(other, "AfnTempSetpoint", weights),
            "AfnWindowAvailability": UmiSchedule.combine(
                self.AfnWindowAvailability, other.AfnWindowAvailability, weights
            ),
            "IsShadingSystemOn": any([self.IsShadingSystemOn, other.IsShadingSystemOn]),
            "IsVirtualPartition": any([self.IsVirtualPartition, other.IsVirtualPartition]),
            "IsZoneMixingOn": any([self.IsZoneMixingOn, other.IsZoneMixingOn]),
            "OperableArea": self.float_mean(other, "OperableArea", weights),
            "ShadingSystemSetpoint": self.float_mean(other, "ShadingSystemSetpoint", weights),
            "ShadingSystemTransmittance": self.float_mean(other, "ShadingSystemTransmittance", weights),
            "ShadingSystemType": max(self.ShadingSystemType, other.ShadingSystemType),
            "ZoneMixingDeltaTemperature": self.float_mean(other, "ZoneMixingDeltaTemperature", weights),
            "ZoneMixingFlowRate": self.float_mean(other, "ZoneMixingFlowRate", weights),
            "ZoneMixingAvailabilitySchedule": UmiSchedule.combine(
                self.ZoneMixingAvailabilitySchedule,
                other.ZoneMixingAvailabilitySchedule,
                weights,
            ),
            "ShadingSystemAvailabilitySchedule": UmiSchedule.combine(
                self.ShadingSystemAvailabilitySchedule,
                other.ShadingSystemAvailabilitySchedule,
                weights,
            ),
            "Type": max(self.Type, other.Type),
        }
        new_obj = WindowSetting(**meta, **new_attr)
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def to_dict(self):
        """Return WindowSetting dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["AfnDischargeC"] = self.AfnDischargeC
        data_dict["AfnTempSetpoint"] = self.AfnTempSetpoint
        data_dict["AfnWindowAvailability"] = self.AfnWindowAvailability.to_ref()
        data_dict["Construction"] = {"$ref": str(self.Construction.id)}
        data_dict["IsShadingSystemOn"] = self.IsShadingSystemOn
        data_dict["IsVirtualPartition"] = self.IsVirtualPartition
        data_dict["IsZoneMixingOn"] = self.IsZoneMixingOn
        data_dict["OperableArea"] = self.OperableArea
        data_dict["ShadingSystemAvailabilitySchedule"] = self.ShadingSystemAvailabilitySchedule.to_ref()
        data_dict["ShadingSystemSetpoint"] = self.ShadingSystemSetpoint
        data_dict["ShadingSystemTransmittance"] = self.ShadingSystemTransmittance
        data_dict["ShadingSystemType"] = self.ShadingSystemType.value
        data_dict["Type"] = self.Type.value
        data_dict["ZoneMixingAvailabilitySchedule"] = self.ZoneMixingAvailabilitySchedule.to_ref()
        data_dict["ZoneMixingDeltaTemperature"] = self.ZoneMixingDeltaTemperature
        data_dict["ZoneMixingFlowRate"] = self.ZoneMixingFlowRate
        data_dict["Category"] = self.Category
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_dict(cls, data, schedules, window_constructions, **kwargs):
        """Create a ZoneConditioning from a dictionary.

        Args:
            data (dict): The python dictionary.
            schedules (dict): A dictionary of UmiSchedules with their id as keys.
            window_constructions (dict): A dictionary of WindowConstruction objects
                with their id as keys.
            **kwargs: keywords passed to parent constructor.
        """
        data = copy(data)
        _id = data.pop("$id")
        afn_availability_schedule = schedules[data.pop("AfnWindowAvailability")["$ref"]]
        construction = window_constructions[data.pop("Construction")["$ref"]]
        shading_system_availability_schedule = schedules[data.pop("ShadingSystemAvailabilitySchedule")["$ref"]]
        zone_mixing_availability_schedule = schedules[data.pop("ZoneMixingAvailabilitySchedule")["$ref"]]
        return cls(
            id=_id,
            Construction=construction,
            AfnWindowAvailability=afn_availability_schedule,
            ShadingSystemAvailabilitySchedule=shading_system_availability_schedule,
            ZoneMixingAvailabilitySchedule=zone_mixing_availability_schedule,
            **data,
            **kwargs,
        )

    @classmethod
    def from_ref(cls, ref, building_templates, schedules, window_constructions, **kwargs):
        """Initialize :class:`WindowSetting` object from a reference id.

        Hint:
            In some cases, the WindowSetting is referenced in the DataStore to the
            Windows property of a BuildingTemplate (instead of being listed in the
            WindowSettings list. This is the case in the original
            BostonTemplateLibrary.json.

        Args:
            ref (str): The referenced number in the json library.
            building_templates (list): List of BuildingTemplates from the datastore.

        Returns:
            WindowSetting: The parsed WindowSetting.
        """
        store = next(
            iter(
                filter(
                    lambda x: x.get("$id") == ref,
                    [bldg.get("Windows") for bldg in building_templates],
                )
            )
        )
        w = cls.from_dict(store, schedules, window_constructions, **kwargs)
        return w

    def validate(self):
        """Validate object and fill in missing values."""
        if self.AfnWindowAvailability is None:
            self.AfnWindowAvailability = UmiSchedule.constant_schedule(value=0, Name="AlwaysOff")
        if self.ShadingSystemAvailabilitySchedule is None:
            self.ShadingSystemAvailabilitySchedule = UmiSchedule.constant_schedule(value=0, Name="AlwaysOff")
        if self.ZoneMixingAvailabilitySchedule is None:
            self.ZoneMixingAvailabilitySchedule = UmiSchedule.constant_schedule(value=0, Name="AlwaysOff")

        return self

    def mapping(self, validate=False):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return {
            "AfnDischargeC": self.AfnDischargeC,
            "AfnTempSetpoint": self.AfnTempSetpoint,
            "AfnWindowAvailability": self.AfnWindowAvailability,
            "Construction": self.Construction,
            "IsShadingSystemOn": self.IsShadingSystemOn,
            "IsVirtualPartition": self.IsVirtualPartition,
            "IsZoneMixingOn": self.IsZoneMixingOn,
            "OperableArea": self.OperableArea,
            "ShadingSystemAvailabilitySchedule": self.ShadingSystemAvailabilitySchedule,
            "ShadingSystemSetpoint": self.ShadingSystemSetpoint,
            "ShadingSystemTransmittance": self.ShadingSystemTransmittance,
            "ShadingSystemType": self.ShadingSystemType,
            "Type": self.Type,
            "ZoneMixingAvailabilitySchedule": self.ZoneMixingAvailabilitySchedule,
            "ZoneMixingDeltaTemperature": self.ZoneMixingDeltaTemperature,
            "ZoneMixingFlowRate": self.ZoneMixingFlowRate,
            "Category": self.Category,
            "Comments": self.Comments,
            "DataSource": self.DataSource,
            "Name": self.Name,
        }

    @property
    def children(self):
        return (
            self.AfnWindowAvailability,
            self.Construction,
            self.ShadingSystemAvailabilitySchedule,
            self.ZoneMixingAvailabilitySchedule,
        )
