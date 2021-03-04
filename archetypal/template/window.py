"""Window module handles window settings."""

import collections
import logging as lg
from enum import Enum
from functools import reduce

from deprecation import deprecated
from eppy.bunch_subclass import EpBunch

import archetypal
from archetypal import calc_simple_glazing, log, timeit
from archetypal.template import MaterialLayer, UmiSchedule, UniqueName
from archetypal.template.gas_material import GasMaterial
from archetypal.template.glazing_material import GlazingMaterial
from archetypal.template.umi_base import UmiBase


class WindowType(Enum):
    """Refers to the window type. Two choices are available: interior or exterior."""

    External = 0
    Internal = 1

    def __lt__(self, other):
        """Return true if self lower than other."""
        return self._value_ < other._value_

    def __gt__(self, other):
        """Return true if self higher than other."""
        return self._value_ > other._value_


class ShadingType(Enum):
    """Refers to window shading types.

    Hint:
        EnergyPlus specifies 8 different shading types, but only 2 are supported
        here: InteriorShade and ExteriorShade. See shading_ for more info.

    .. _shading: https://bigladdersoftware.com/epx/docs/8-4/input-output-reference/group-thermal-zone-description-geometry.html#field-shading-type
    """

    ExteriorShade = 0
    InteriorShade = 1

    def __lt__(self, other):
        """Return true if self lower than other."""
        return self._value_ < other._value_

    def __gt__(self, other):
        """Return true if self higher than other."""
        return self._value_ > other._value_


class WindowConstruction(UmiBase):
    """Window Construction.

    .. image:: ../images/template/constructions-window.png
    """

    def __init__(
        self,
        Category="Double",
        AssemblyCarbon=0,
        AssemblyCost=0,
        AssemblyEnergy=0,
        DisassemblyCarbon=0,
        DisassemblyEnergy=0,
        Layers=None,
        **kwargs,
    ):
        """Initialize a WindowConstruction.

        Args:
            Category (str): "Single", "Double" or "Triple".
            AssemblyCarbon (float): Assembly Embodied Carbon by m2 of
                construction.
            AssemblyCost (float): Assembly cost by m2 of construction.
            AssemblyEnergy (float): Assembly Embodied Energy by m2; of
                construction.
            DisassemblyCarbon (float): Disassembly embodied carbon by m2 of
                construction.
            DisassemblyEnergy (float): Disassembly embodied energy by m2 of
                construction.
            Layers (list of MaterialLayer):
            **kwargs: Other keywords passed to the constructor.
        """
        super(WindowConstruction, self).__init__(**kwargs)
        self.Category = Category
        self.DisassemblyEnergy = DisassemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.AssemblyEnergy = AssemblyEnergy
        self.AssemblyCost = AssemblyCost
        self.AssemblyCarbon = AssemblyCarbon
        self.Layers = Layers

    def __hash__(self):
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        if not isinstance(other, WindowConstruction):
            return NotImplemented
        else:
            return all(
                [
                    self.Category == other.Category,
                    self.AssemblyCarbon == other.AssemblyCarbon,
                    self.AssemblyCost == other.AssemblyCost,
                    self.AssemblyEnergy == other.AssemblyEnergy,
                    self.DisassemblyCarbon == other.DisassemblyCarbon,
                    self.DisassemblyEnergy == other.DisassemblyEnergy,
                    self.Layers == other.Layers,
                ]
            )

    @classmethod
    @deprecated(
        deprecated_in="1.3.1",
        removed_in="1.5",
        current_version=archetypal.__version__,
        details="Use from_dict function instead",
    )
    def from_json(cls, *args, **kwargs):

        return cls.from_dict(*args, **kwargs)

    @classmethod
    def from_dict(cls, *args, **kwargs):
        """Create :class:`WindowConstruction` object from json dict."""
        wc = cls(*args, **kwargs)
        layers = kwargs.get("Layers", None)

        # resolve Material objects from ref
        wc.Layers = [
            MaterialLayer(wc.get_ref(layer["Material"]), layer["Thickness"])
            for layer in layers
        ]
        return wc

    @classmethod
    def from_epbunch(cls, Construction, **kwargs):
        """Create :class:`WindowConstruction` object from idf Construction object.

        Example:
            >>> from archetypal import IDF
            >>> from archetypal.template import WindowSetting
            >>> idf = IDF("myidf.idf")
            >>> construction_name = "Some construction name"
            >>> WindowConstruction.from_epbunch(Name=construction_name,
            >>> idf=idf)

        Args:
            Construction (EpBunch): The Construction epbunch object.
            **kwargs: Other keywords passed to the constructor.
        """
        Name = Construction.Name
        idf = Construction.theidf
        wc = cls(Name=Name, idf=idf, **kwargs)
        wc.Layers = wc.layers(Construction, **kwargs)
        catdict = {0: "Single", 1: "Single", 2: "Double", 3: "Triple", 4: "Quadruple"}
        wc.Category = catdict[
            len([lyr for lyr in wc.Layers if isinstance(lyr.Material, GlazingMaterial)])
        ]
        return wc

    def to_json(self):
        """Convert class properties to dict."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Layers"] = [layer.to_dict() for layer in self.Layers]
        data_dict["AssemblyCarbon"] = self.AssemblyCarbon
        data_dict["AssemblyCost"] = self.AssemblyCost
        data_dict["AssemblyEnergy"] = self.AssemblyEnergy
        data_dict["DisassemblyCarbon"] = self.DisassemblyCarbon
        data_dict["DisassemblyEnergy"] = self.DisassemblyEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    def mapping(self):
        self.validate()

        return dict(
            Layers=self.Layers,
            AssemblyCarbon=self.AssemblyCarbon,
            AssemblyCost=self.AssemblyCost,
            AssemblyEnergy=self.AssemblyEnergy,
            DisassemblyCarbon=self.DisassemblyCarbon,
            DisassemblyEnergy=self.DisassemblyEnergy,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def layers(self, Construction, **kwargs):
        """Retrieve layers for the WindowConstruction"""
        layers = []
        for field in Construction.fieldnames:
            # Loop through the layers from the outside layer towards the
            # indoor layers and get the material they are made of.
            material = Construction.get_referenced_object(field) or kwargs.get(
                "material", None
            )
            if material:
                # Create the WindowMaterial:Glazing or the WindowMaterial:Gas
                # and append to the list of layers
                if material.key.upper() == "WindowMaterial:Glazing".upper():
                    material_obj = GlazingMaterial(
                        Conductivity=material.Conductivity,
                        SolarTransmittance=material.Solar_Transmittance_at_Normal_Incidence,
                        SolarReflectanceFront=material.Front_Side_Solar_Reflectance_at_Normal_Incidence,
                        SolarReflectanceBack=material.Back_Side_Solar_Reflectance_at_Normal_Incidence,
                        VisibleTransmittance=material.Visible_Transmittance_at_Normal_Incidence,
                        VisibleReflectanceFront=material.Front_Side_Visible_Reflectance_at_Normal_Incidence,
                        VisibleReflectanceBack=material.Back_Side_Visible_Reflectance_at_Normal_Incidence,
                        IRTransmittance=material.Infrared_Transmittance_at_Normal_Incidence,
                        IREmissivityFront=material.Front_Side_Infrared_Hemispherical_Emissivity,
                        IREmissivityBack=material.Back_Side_Infrared_Hemispherical_Emissivity,
                        DirtFactor=material.Dirt_Correction_Factor_for_Solar_and_Visible_Transmittance,
                        Type="Uncoated",
                        Name=material.Name,
                        Optical=material.Optical_Data_Type,
                        OpticalData=material.Window_Glass_Spectral_Data_Set_Name,
                        idf=self.idf,
                    )

                    material_layer = MaterialLayer(material_obj, material.Thickness)

                elif material.key.upper() == "WindowMaterial:Gas".upper():
                    # Todo: Make gas name generic, like in UmiTemplateLibrary Editor
                    material_obj = GasMaterial(
                        Name=material.Gas_Type.upper(), idf=self.idf
                    )
                    material_layer = MaterialLayer(material_obj, material.Thickness)
                elif material.key.upper() == "WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM":
                    glass_properties = calc_simple_glazing(
                        material.Solar_Heat_Gain_Coefficient,
                        material.UFactor,
                        material.Visible_Transmittance,
                    )
                    material_obj = GlazingMaterial(
                        **glass_properties, Name=material.Name, idf=self.idf
                    )

                    material_layer = MaterialLayer(
                        material_obj, glass_properties["Thickness"]
                    )
                    layers.append(material_layer)
                    break
                else:
                    continue

                layers.append(material_layer)
        return layers

    def combine(self, other, weights=None):
        """Append other to self. Return self + other as a new object.

        For now, simply returns self.

        todo:
            - Implement equivalent window layers for constant u-factor.

        """
        # Check if other is None. Simply return self
        if not other:
            return self

        if not self:
            return other

        return self

    def validate(self):
        """Validate object and fill in missing values.

        todo:
            - Implement validation
        """
        return self

    def get_ref(self, ref):
        """Get item matching reference id."""
        return next(
            iter(
                [
                    value
                    for value in WindowConstruction.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )


class WindowSetting(UmiBase):
    """Window Settings define the various window-related properties of a
    specific :class:`Zone`. Control natural ventilation, shading and airflow
    networks and more using this class. This class serves the same role as the
    ZoneInformation>Windows tab in the UMI TemplateEditor.

    .. image:: ../images/template/zoneinfo-windows.png

    Hint:
        The WindowSetting class implements two constructors that are tailored to
        the eppy_ scripting language:

        - :func:`from_construction` and
        - :func:`from_surface`.

    .. _eppy : https://eppy.readthedocs.io/en/latest/
    """

    def __init__(
        self,
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
        **kwargs,
    ):
        """Initialize a WindowSetting using default values:

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
        super(WindowSetting, self).__init__(**kwargs)

        self.ZoneMixingAvailabilitySchedule = ZoneMixingAvailabilitySchedule
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

    @property
    def OperableArea(self):
        return self._operable_area

    @OperableArea.setter
    def OperableArea(self, value):
        if value > 1:
            raise ValueError("Operable Area must be a number between 0 and 1.")
        self._operable_area = value

    @property
    def AfnDischargeC(self):
        return float(self._afn_discharge_c)

    @AfnDischargeC.setter
    def AfnDischargeC(self, value):
        if value > 1:
            raise ValueError("Operable Area must be a number between 0 and 1.")
        self._afn_discharge_c = value

    @property
    def AfnTempSetpoint(self):
        return float(self._afn_temp_setpoint)

    @AfnTempSetpoint.setter
    def AfnTempSetpoint(self, value):
        self._afn_temp_setpoint = value

    @property
    def ShadingSystemSetpoint(self):
        return float(self._shading_system_setpoint)

    @ShadingSystemSetpoint.setter
    def ShadingSystemSetpoint(self, value):
        self._shading_system_setpoint = value

    @property
    def ShadingSystemTransmittance(self):
        return float(self._shading_system_transmittance)

    @ShadingSystemTransmittance.setter
    def ShadingSystemTransmittance(self, value):
        self._shading_system_transmittance = value

    def __add__(self, other):
        return self.combine(other)

    def __repr__(self):
        # header = "{}: <{}>\n".format(self.Name, self.__class__.mro()[0].__name__)
        # return header + tabulate.tabulate(self.mapping().items(), tablefmt="plain")
        return super(WindowSetting, self).__repr__()

    def __str__(self):
        return repr(self)

    def __hash__(self):
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __eq__(self, other):
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
    def generic(cls, idf, Name):
        """Initialize a generic window with SHGC=0.704, UFactor=2.703, Tvis=0.786.

        Args:
            Name (str): Name of the WindowSetting
            idf (IDF):
        """
        material = idf.anidfobject(
            "WindowMaterial:SimpleGlazingSystem".upper(),
            Name="SimpleWindow:SINGLE PANE HW WINDOW",
            UFactor=2.703,
            Solar_Heat_Gain_Coefficient=0.704,
            Visible_Transmittance=0.786,
        )

        constr = idf.anidfobject(
            "CONSTRUCTION",
            Name="SINGLE PANE HW WINDOW",
            Outside_Layer="SimpleWindow:SINGLE PANE HW WINDOW",
        )
        return cls.from_construction(Name=Name, Construction=constr, material=material)

    @classmethod
    def from_construction(cls, Construction, **kwargs):
        """Make a :class:`WindowSetting` directly from a Construction_ object.

        .. _Construction : https://bigladdersoftware.com/epx/docs/8-9/input-output-reference/group-surface-construction-elements.html#construction-000

        Examples:
            >>> from archetypal import IDF
            >>> from archetypal.template import WindowSetting
            >>> # Given an IDF object
            >>> idf = IDF("idfname.idf")
            >>> construction = idf.getobject('CONSTRUCTION',
            >>>                              'AEDG-SmOffice 1A Window Fixed')
            >>> WindowSetting.from_construction(Name='test_window',
            >>>                    Construction=construction)

        Args:
            Construction (EpBunch): The construction name for this window.
            **kwargs: Other keywords passed to the constructor.

        Returns:
            (windowSetting): The window setting object.
        """
        name = kwargs.pop("Name", Construction.Name + "_Window")
        w = cls(Name=name, idf=Construction.theidf, **kwargs)
        w.Construction = WindowConstruction.from_epbunch(Construction, **kwargs)
        w.AfnWindowAvailability = UmiSchedule.constant_schedule(idf=w.idf)
        w.ShadingSystemAvailabilitySchedule = UmiSchedule.constant_schedule(idf=w.idf)
        w.ZoneMixingAvailabilitySchedule = UmiSchedule.constant_schedule(idf=w.idf)
        return w

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
            construction = surface.get_referenced_object("Construction_Name")
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
                attr["ShadingSystemAvailabilitySchedule"] = UmiSchedule(
                    Name=name, idf=surface.theidf
                )
            else:
                # Determine which behavior of control
                shade_ctrl_type = shading_control["Shading_Control_Type"]
                if shade_ctrl_type.lower() == "alwaysoff":
                    attr[
                        "ShadingSystemAvailabilitySchedule"
                    ] = UmiSchedule.constant_schedule(
                        name="AlwaysOff", hourly_value=0, idf=surface.theidf
                    )
                elif shade_ctrl_type.lower() == "alwayson":
                    attr[
                        "ShadingSystemAvailabilitySchedule"
                    ] = UmiSchedule.constant_schedule(idf=surface.theidf)
                else:
                    log(
                        'Window "{}" uses a  window control type that '
                        'is not supported: "{}". Reverting to '
                        '"AlwaysOn"'.format(surface.Name, shade_ctrl_type),
                        lg.WARN,
                    )
                    attr[
                        "ShadingSystemAvailabilitySchedule"
                    ] = UmiSchedule.constant_schedule(idf=surface.theidf)
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
            attr["ShadingSystemAvailabilitySchedule"] = UmiSchedule.constant_schedule(
                idf=surface.theidf
            )

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
                attr["AfnWindowAvailability"] = UmiSchedule(
                    Name=name, idf=surface.theidf
                )
            else:
                attr["AfnWindowAvailability"] = UmiSchedule.constant_schedule(
                    idf=surface.theidf
                )
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
                hourly_value=0, Name="AlwaysOff", idf=surface.theidf
            )
        # Todo: Zone Mixing is always off
        attr["ZoneMixingAvailabilitySchedule"] = UmiSchedule.constant_schedule(
            hourly_value=0, Name="AlwaysOff", idf=surface.theidf
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

        for surf in zone._zonesurfaces:
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
            AfnDischargeC=self._float_mean(other, "AfnDischargeC", weights),
            AfnTempSetpoint=self._float_mean(other, "AfnTempSetpoint", weights),
            AfnWindowAvailability=UmiSchedule.combine(
                self.AfnWindowAvailability, other.AfnWindowAvailability, weights
            ),
            IsShadingSystemOn=any([self.IsShadingSystemOn, other.IsShadingSystemOn]),
            IsVirtualPartition=any([self.IsVirtualPartition, other.IsVirtualPartition]),
            IsZoneMixingOn=any([self.IsZoneMixingOn, other.IsZoneMixingOn]),
            OperableArea=self._float_mean(other, "OperableArea", weights),
            ShadingSystemSetpoint=self._float_mean(
                other, "ShadingSystemSetpoint", weights
            ),
            ShadingSystemTransmittance=self._float_mean(
                other, "ShadingSystemTransmittance", weights
            ),
            ShadingSystemType=max(self.ShadingSystemType, other.ShadingSystemType),
            ZoneMixingDeltaTemperature=self._float_mean(
                other, "ZoneMixingDeltaTemperature", weights
            ),
            ZoneMixingFlowRate=self._float_mean(other, "ZoneMixingFlowRate", weights),
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
        new_obj = WindowSetting(**meta, **new_attr, idf=self.idf)
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def to_json(self):
        """Convert class properties to dict."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["AfnDischargeC"] = self.AfnDischargeC
        data_dict["AfnTempSetpoint"] = self.AfnTempSetpoint
        data_dict["AfnWindowAvailability"] = self.AfnWindowAvailability.to_dict()
        data_dict["Construction"] = {"$ref": str(self.Construction.id)}
        data_dict["IsShadingSystemOn"] = self.IsShadingSystemOn
        data_dict["IsVirtualPartition"] = self.IsVirtualPartition
        data_dict["IsZoneMixingOn"] = self.IsZoneMixingOn
        data_dict["OperableArea"] = self.OperableArea
        data_dict[
            "ShadingSystemAvailabilitySchedule"
        ] = self.ShadingSystemAvailabilitySchedule.to_dict()
        data_dict["ShadingSystemSetpoint"] = self.ShadingSystemSetpoint
        data_dict["ShadingSystemTransmittance"] = self.ShadingSystemTransmittance
        data_dict["ShadingSystemType"] = self.ShadingSystemType.value
        data_dict["Type"] = self.Type.value
        data_dict[
            "ZoneMixingAvailabilitySchedule"
        ] = self.ZoneMixingAvailabilitySchedule.to_dict()
        data_dict["ZoneMixingDeltaTemperature"] = self.ZoneMixingDeltaTemperature
        data_dict["ZoneMixingFlowRate"] = self.ZoneMixingFlowRate
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    @classmethod
    @deprecated(
        deprecated_in="1.3.1",
        removed_in="1.5",
        current_version=archetypal.__version__,
        details="Use from_dict function instead",
    )
    def from_json(cls, *args, **kwargs):

        return cls.from_dict(*args, **kwargs)

    @classmethod
    def from_dict(cls, *args, **kwargs):
        """Initialize :class:`WindowSetting` object from json dict."""
        w = cls(*args, **kwargs)

        ref = kwargs.get("AfnWindowAvailability", None)
        w.AfnWindowAvailability = w.get_ref(ref)
        ref = kwargs.get("Construction", None)
        w.Construction = w.get_ref(ref)
        ref = kwargs.get("ShadingSystemAvailabilitySchedule", None)
        w.ShadingSystemAvailabilitySchedule = w.get_ref(ref)
        ref = kwargs.get("ZoneMixingAvailabilitySchedule", None)
        w.ZoneMixingAvailabilitySchedule = w.get_ref(ref)
        return w

    @classmethod
    def from_ref(cls, ref, building_templates, idf=None, **kwargs):
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
        w = cls.from_json(**store, idf=idf, **kwargs)
        return w

    def validate(self):
        """Validate object and fill in missing values."""
        if not self.AfnWindowAvailability:
            self.AfnWindowAvailability = UmiSchedule.constant_schedule(
                hourly_value=0, Name="AlwaysOff", idf=self.idf
            )
        if not self.ShadingSystemAvailabilitySchedule:
            self.ShadingSystemAvailabilitySchedule = UmiSchedule.constant_schedule(
                hourly_value=0, Name="AlwaysOff", idf=self.idf
            )
        if not self.ZoneMixingAvailabilitySchedule:
            self.ZoneMixingAvailabilitySchedule = UmiSchedule.constant_schedule(
                hourly_value=0, Name="AlwaysOff", idf=self.idf
            )

        return self

    def mapping(self):
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

    def get_ref(self, ref):
        """Get item matching reference id.

        Args:
            ref:
        """
        return next(
            iter(
                [
                    value
                    for value in WindowSetting.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )
