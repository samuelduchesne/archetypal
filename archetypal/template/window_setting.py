"""archetypal WindowSettings."""

import collections
import logging as lg
from copy import copy
from functools import reduce

from validator_collection import checkers, validators
from validator_collection.errors import EmptyValueError

from archetypal.template.constructions.window_construction import (
    ShadingType,
    WindowConstruction,
    WindowType,
)
from archetypal.template.schedule import UmiSchedule
from archetypal.template.umi_base import UmiBase
from archetypal.utils import log, timeit


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
        super(WindowSetting, self).__init__(Name, **kwargs)

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
        self.ShadingSystemType = ShadingType(ShadingSystemType)
        self.Type = WindowType(Type)
        self.ZoneMixingDeltaTemperature = ZoneMixingDeltaTemperature
        self.ZoneMixingFlowRate = ZoneMixingFlowRate
        self.ZoneMixingAvailabilitySchedule = ZoneMixingAvailabilitySchedule

        self.area = area

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
                f"Input error with value {value}. AfnWindowAvailability must "
                f"be an UmiSchedule, not a {type(value)}"
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
                f"Input value error for '{value}'. "
                f"Expected one of {tuple(a for a in ShadingType)}"
            )
            self._shading_system_type = ShadingType[value]
        elif checkers.is_numeric(value):
            assert ShadingType[value], (
                f"Input value error for '{value}'. "
                f"Expected one of {tuple(a for a in ShadingType)}"
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
        self._shading_system_transmittance = validators.float(
            value, minimum=0, maximum=1
        )

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
            f"Input error with value {value}. IsShadingSystemOn must "
            f"be a boolean, not a {type(value)}"
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
                f"Input error with value {value}. Construction must "
                f"be an WindowConstruction, not a {type(value)}"
            )
        self._construction = value

    @property
    def IsVirtualPartition(self):
        """Get or set the state of the virtual partition."""
        return self._is_virtual_partition

    @IsVirtualPartition.setter
    def IsVirtualPartition(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsVirtualPartition must "
            f"be a boolean, not a {type(value)}"
        )
        self._is_virtual_partition = value

    @property
    def IsZoneMixingOn(self):
        """Get or set mixing in zone."""
        return self._is_zone_mixing_on

    @IsZoneMixingOn.setter
    def IsZoneMixingOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsZoneMixingOn must "
            f"be a boolean, not a {type(value)}"
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
                f"Input value error for '{value}'. "
                f"Expected one of {tuple(a for a in WindowType)}"
            )
            self._type = WindowType[value]
        elif checkers.is_numeric(value):
            assert WindowType[value], (
                f"Input value error for '{value}'. "
                f"Expected one of {tuple(a for a in WindowType)}"
            )
            self._type = WindowType(value)
        elif isinstance(value, WindowType):
            self._type = value

    def __add__(self, other):
        """Combine self and other."""
        return self.combine(other)

    def __repr__(self):
        """Return a representation of self."""
        return super(WindowSetting, self).__repr__()

    def __str__(self):
        """Return string representation."""
        return repr(self)

    def __hash__(self):
        """Return the hash value of self."""
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

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
                    self.ShadingSystemAvailabilitySchedule
                    == other.ShadingSystemAvailabilitySchedule,
                    self.ShadingSystemSetpoint == other.ShadingSystemSetpoint,
                    self.ShadingSystemTransmittance == other.ShadingSystemTransmittance,
                    self.ShadingSystemType == other.ShadingSystemType,
                    self.Type == other.Type,
                    self.IsZoneMixingOn == other.IsZoneMixingOn,
                    self.ZoneMixingAvailabilitySchedule
                    == other.ZoneMixingAvailabilitySchedule,
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
    def from_construction(cls, Construction, **kwargs):
        """Make a :class:`WindowSetting` directly from a Construction_ object.

        .. _Construction : https://bigladdersoftware.com/epx/docs/8-9/input-output-reference/group-surface-construction-elements.html#construction-000

        Examples:
            >>> from archetypal import IDF
            >>> from archetypal.template.window_setting import WindowSetting
            >>> # Given an IDF object
            >>> idf = IDF("idfname.idf")
            >>> constr = idf.getobject('CONSTRUCTION',
            >>>                              'AEDG-SmOffice 1A Window Fixed')
            >>> WindowSetting.from_construction(
            >>>     Name='test_window',
            >>>     Construction=constr
            >>> )

        Args:
            Construction (EpBunch): The construction name for this window.
            **kwargs: Other keywords passed to the constructor.

        Returns:
            (windowSetting): The window setting object.
        """
        name = kwargs.pop("Name", Construction.Name + "_Window")
        construction = WindowConstruction.from_epbunch(Construction, **kwargs)
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
    def from_surface(cls, surface, **kwargs):
        """Build a WindowSetting object from a FenestrationSurface:Detailed_.

        This constructor will detect common window constructions and
        shading devices. Supported Shading and Natural Air flow EnergyPlus
        objects are: WindowProperty:ShadingControl_,
        AirflowNetwork:MultiZone:Surface_.

        Important:
            If an EnergyPlus object is not supported, eg.:
            AirflowNetwork:MultiZone:Component:DetailedOpening_, only a warning
            will be issued in the console for the related object instance and
            default values will be automatically used.

        .. _FenestrationSurface:Detailed:
           https://bigladdersoftware.com/epx/docs/8-9/input-output-reference
           /group-thermal-zone-description-geometry.html
           #fenestrationsurfacedetailed
        .. _WindowProperty:ShadingControl:
           https://bigladdersoftware.com/epx/docs/8-9/input-output-reference
           /group-thermal-zone-description-geometry.html
           #windowpropertyshadingcontrol
        .. _AirflowNetwork:MultiZone:Surface:
           https://bigladdersoftware.com/epx/docs/8-9/input-output-reference
           /group-airflow-network.html#airflownetworkmultizonesurface
        .. _AirflowNetwork:MultiZone:Component:DetailedOpening:
           https://bigladdersoftware.com/epx/docs/8-9/input-output-reference
           /group-airflow-network.html
           #airflownetworkmultizonecomponentdetailedopening

        Args:
            surface (EpBunch): The FenestrationSurface:Detailed_ object.

        Returns:
            (WindowSetting): The window setting object.
        """
        if surface.key.upper() == "FENESTRATIONSURFACE:DETAILED":
            if not surface.Surface_Type.lower() == "window":
                return  # Other surface types (Doors, GlassDoors, etc.) are ignored.
            construction = surface.get_referenced_object("Construction_Name")
            if construction is None:
                construction = surface.theidf.getobject(
                    "CONSTRUCTION", surface.Construction_Name
                )
            construction = WindowConstruction.from_epbunch(construction)
            shading_control = surface.get_referenced_object("Shading_Control_Name")
        elif surface.key.upper() == "WINDOW":
            construction = surface.get_referenced_object("Construction_Name")
            construction = WindowConstruction.from_epbunch(construction)
            shading_control = next(
                iter(
                    surface.getreferingobjs(
                        iddgroups=["Thermal Zones and Surfaces"],
                        fields=[f"Fenestration_Surface_{i}_Name" for i in range(1, 10)],
                    )
                ),
                None,
            )
        elif surface.key.upper() == "DOOR":
            return  # Simply skip doors.
        else:
            raise ValueError(
                f"A window of type {surface.key} is not yet supported. "
                f"Please contact developers"
            )

        attr = {}
        if shading_control:
            # a WindowProperty:ShadingControl_ object can be attached to
            # this window
            attr["IsShadingSystemOn"] = True
            if shading_control["Setpoint"] != "":
                attr["ShadingSystemSetpoint"] = shading_control["Setpoint"]
            shade_mat = shading_control.get_referenced_object(
                "Shading_Device_Material_Name"
            )
            # get shading transmittance
            if shade_mat:
                attr["ShadingSystemTransmittance"] = shade_mat["Visible_Transmittance"]
            # get shading control schedule
            if shading_control["Shading_Control_Is_Scheduled"].upper() == "YES":
                name = shading_control["Schedule_Name"]
                attr["ShadingSystemAvailabilitySchedule"] = UmiSchedule.from_epbunch(
                    surface.theidf.schedules_dict[name.upper()]
                )
            else:
                # Determine which behavior of control
                shade_ctrl_type = shading_control["Shading_Control_Type"]
                if shade_ctrl_type.lower() == "alwaysoff":
                    attr[
                        "ShadingSystemAvailabilitySchedule"
                    ] = UmiSchedule.constant_schedule(value=0, name="AlwaysOff")
                elif shade_ctrl_type.lower() == "alwayson":
                    attr[
                        "ShadingSystemAvailabilitySchedule"
                    ] = UmiSchedule.constant_schedule()
                else:
                    log(
                        'Window "{}" uses a  window control type that '
                        'is not supported: "{}". Reverting to '
                        '"AlwaysOn"'.format(surface.Name, shade_ctrl_type),
                        lg.WARN,
                    )
                    attr[
                        "ShadingSystemAvailabilitySchedule"
                    ] = UmiSchedule.constant_schedule()
            # get shading type
            if shading_control["Shading_Type"] != "":
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
                attr["ShadingSystemType"] = mapping[shading_control["Shading_Type"]]
        else:
            # Set default schedules
            attr["ShadingSystemAvailabilitySchedule"] = UmiSchedule.constant_schedule()

        # get airflow network
        afn = next(
            iter(
                surface.getreferingobjs(
                    iddgroups=["Natural Ventilation and Duct Leakage"],
                    fields=["Surface_Name"],
                )
            ),
            None,
        )

        if afn:
            attr["OperableArea"] = afn.WindowDoor_Opening_Factor_or_Crack_Factor
            leak = afn.get_referenced_object("Leakage_Component_Name")
            name = afn["Venting_Availability_Schedule_Name"]
            if name != "":
                attr["AfnWindowAvailability"] = UmiSchedule.from_epbunch(
                    surface.theidf.schedules_dict[name.upper()]
                )
            else:
                attr["AfnWindowAvailability"] = UmiSchedule.constant_schedule()
            name = afn["Ventilation_Control_Zone_Temperature_Setpoint_Schedule_Name"]
            if name != "":
                attr["AfnTempSetpoint"] = UmiSchedule(
                    Name=name, idf=surface.theidf
                ).mean
            else:
                pass  # uses default

            if (
                leak.key.upper()
                == "AIRFLOWNETWORK:MULTIZONE:SURFACE:EFFECTIVELEAKAGEAREA"
            ):
                attr["AfnDischargeC"] = leak["Discharge_Coefficient"]
            elif (
                leak.key.upper()
                == "AIRFLOWNETWORK:MULTIZONE:COMPONENT:HORIZONTALOPENING"
            ):
                log(
                    '"{}" is not fully supported. Reverting to '
                    'defaults for object "{}"'.format(leak.key, cls.mro()[0].__name__),
                    lg.WARNING,
                )
            elif leak.key.upper() == "AIRFLOWNETWORK:MULTIZONE:SURFACE:CRACK":
                log(
                    '"{}" is not fully supported. Rerverting to '
                    'defaults for object "{}"'.format(leak.key, cls.mro()[0].__name__),
                    lg.WARNING,
                )
            elif (
                leak.key.upper() == "AIRFLOWNETWORK:MULTIZONE:COMPONENT:DETAILEDOPENING"
            ):
                log(
                    '"{}" is not fully supported. Rerverting to '
                    'defaults for object "{}"'.format(leak.key, cls.mro()[0].__name__),
                    lg.WARNING,
                )
            elif (
                leak.key.upper() == "AIRFLOWNETWORK:MULTIZONE:COMPONENT:ZONEEXHAUSTFAN"
            ):
                log(
                    '"{}" is not fully supported. Rerverting to '
                    'defaults for object "{}"'.format(leak.key, cls.mro()[0].__name__),
                    lg.WARNING,
                )
            elif leak.key.upper() == "AIRFLOWNETWORK:MULTIZONE:COMPONENT:SIMPLEOPENING":
                log(
                    '"{}" is not fully supported. Rerverting to '
                    'defaults for object "{}"'.format(leak.key, cls.mro()[0].__name__),
                    lg.WARNING,
                )
        else:
            attr["AfnWindowAvailability"] = UmiSchedule.constant_schedule(
                value=0, Name="AlwaysOff"
            )
        # Todo: Zone Mixing is always off
        attr["ZoneMixingAvailabilitySchedule"] = UmiSchedule.constant_schedule(
            value=0, Name="AlwaysOff"
        )
        DataSource = kwargs.pop("DataSource", surface.theidf.name)
        Category = kwargs.pop("Category", surface.theidf.name)
        w = cls(
            Name=surface.Name,
            Construction=construction,
            idf=surface.theidf,
            Category=Category,
            DataSource=DataSource,
            **attr,
            **kwargs,
        )
        return w

    @classmethod
    @timeit
    def from_zone(cls, zone, **kwargs):
        """Iterate over the zone subsurfaces and create a window object.

        If more than one window is created, use reduce to combine them together.

        Args:
            zone (Zone): The Zone object from which the WindowSetting is
                created.

        Returns:
            WindowSetting: The WindowSetting object for this zone.
        """
        window_sets = []

        for surf in zone.zone_surfaces:
            # skip internalmass objects since they don't have windows.
            if surf.key.lower() != "internalmass":
                for subsurf in surf.subsurfaces:
                    # For each subsurface, create a WindowSetting object
                    # using the `from_surface` constructor.
                    window_sets.append(cls.from_surface(subsurf, **kwargs))

        if window_sets:
            # if one or more window has been created, reduce. Using reduce on
            # a len==1 list, will simply return the object.

            return reduce(WindowSetting.combine, window_sets)
        else:
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
            msg = "Cannot combine %s with %s" % (
                self.__class__.__name__,
                other.__class__.__name__,
            )
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        if not weights:
            log(
                'using 1 as weighting factor in "{}" '
                "combine.".format(self.__class__.__name__)
            )
            weights = [1.0, 1.0]
        meta = self._get_predecessors_meta(other)
        new_attr = dict(
            Construction=WindowConstruction.combine(
                self.Construction, other.Construction, weights
            ),
            AfnDischargeC=self.float_mean(other, "AfnDischargeC", weights),
            AfnTempSetpoint=self.float_mean(other, "AfnTempSetpoint", weights),
            AfnWindowAvailability=UmiSchedule.combine(
                self.AfnWindowAvailability, other.AfnWindowAvailability, weights
            ),
            IsShadingSystemOn=any([self.IsShadingSystemOn, other.IsShadingSystemOn]),
            IsVirtualPartition=any([self.IsVirtualPartition, other.IsVirtualPartition]),
            IsZoneMixingOn=any([self.IsZoneMixingOn, other.IsZoneMixingOn]),
            OperableArea=self.float_mean(other, "OperableArea", weights),
            ShadingSystemSetpoint=self.float_mean(
                other, "ShadingSystemSetpoint", weights
            ),
            ShadingSystemTransmittance=self.float_mean(
                other, "ShadingSystemTransmittance", weights
            ),
            ShadingSystemType=max(self.ShadingSystemType, other.ShadingSystemType),
            ZoneMixingDeltaTemperature=self.float_mean(
                other, "ZoneMixingDeltaTemperature", weights
            ),
            ZoneMixingFlowRate=self.float_mean(other, "ZoneMixingFlowRate", weights),
            ZoneMixingAvailabilitySchedule=UmiSchedule.combine(
                self.ZoneMixingAvailabilitySchedule,
                other.ZoneMixingAvailabilitySchedule,
                weights,
            ),
            ShadingSystemAvailabilitySchedule=UmiSchedule.combine(
                self.ShadingSystemAvailabilitySchedule,
                other.ShadingSystemAvailabilitySchedule,
                weights,
            ),
            Type=max(self.Type, other.Type),
        )
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
        data_dict[
            "ShadingSystemAvailabilitySchedule"
        ] = self.ShadingSystemAvailabilitySchedule.to_ref()
        data_dict["ShadingSystemSetpoint"] = self.ShadingSystemSetpoint
        data_dict["ShadingSystemTransmittance"] = self.ShadingSystemTransmittance
        data_dict["ShadingSystemType"] = self.ShadingSystemType.value
        data_dict["Type"] = self.Type.value
        data_dict[
            "ZoneMixingAvailabilitySchedule"
        ] = self.ZoneMixingAvailabilitySchedule.to_ref()
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
        shading_system_availability_schedule = schedules[
            data.pop("ShadingSystemAvailabilitySchedule")["$ref"]
        ]
        zone_mixing_availability_schedule = schedules[
            data.pop("ZoneMixingAvailabilitySchedule")["$ref"]
        ]
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
    def from_ref(
        cls, ref, building_templates, schedules, window_constructions, **kwargs
    ):
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
        if not self.AfnWindowAvailability:
            self.AfnWindowAvailability = UmiSchedule.constant_schedule(
                value=0, Name="AlwaysOff"
            )
        if not self.ShadingSystemAvailabilitySchedule:
            self.ShadingSystemAvailabilitySchedule = UmiSchedule.constant_schedule(
                value=0, Name="AlwaysOff"
            )
        if not self.ZoneMixingAvailabilitySchedule:
            self.ZoneMixingAvailabilitySchedule = UmiSchedule.constant_schedule(
                value=0, Name="AlwaysOff"
            )

        return self

    def mapping(self, validate=True):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return dict(
            AfnDischargeC=self.AfnDischargeC,
            AfnTempSetpoint=self.AfnTempSetpoint,
            AfnWindowAvailability=self.AfnWindowAvailability,
            Construction=self.Construction,
            IsShadingSystemOn=self.IsShadingSystemOn,
            IsVirtualPartition=self.IsVirtualPartition,
            IsZoneMixingOn=self.IsZoneMixingOn,
            OperableArea=self.OperableArea,
            ShadingSystemAvailabilitySchedule=self.ShadingSystemAvailabilitySchedule,
            ShadingSystemSetpoint=self.ShadingSystemSetpoint,
            ShadingSystemTransmittance=self.ShadingSystemTransmittance,
            ShadingSystemType=self.ShadingSystemType,
            Type=self.Type,
            ZoneMixingAvailabilitySchedule=self.ZoneMixingAvailabilitySchedule,
            ZoneMixingDeltaTemperature=self.ZoneMixingDeltaTemperature,
            ZoneMixingFlowRate=self.ZoneMixingFlowRate,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )
