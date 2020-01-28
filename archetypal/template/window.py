################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import logging as lg
from enum import IntEnum
from functools import reduce

import tabulate
from archetypal import log, IDF, calc_simple_glazing, timeit
from archetypal.template import MaterialLayer, UmiSchedule, UniqueName
from archetypal.template.gas_material import GasMaterial
from archetypal.template.glazing_material import GlazingMaterial
from archetypal.template.umi_base import UmiBase, Unique
from eppy.bunch_subclass import EpBunch


class WindowConstruction(UmiBase, metaclass=Unique):
    """
    $id, AssemblyCarbon, AssemblyCost, AssemblyEnergy, Category, Comments,
    DataSource, DisassemblyCarbon, DisassemblyEnergy, Layers, Name, Type
    """

    def __init__(
        self,
        Category="Double",
        AssemblyCarbon=0,
        AssemblyCost=0,
        AssemblyEnergy=0,
        DisassemblyCarbon=0,
        DisassemblyEnergy=0,
        **kwargs
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
            **kwargs: Other keywords passed to the constructor.
        """
        super(WindowConstruction, self).__init__(**kwargs)
        self.Category = Category
        self.DisassemblyEnergy = DisassemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.AssemblyEnergy = AssemblyEnergy
        self.AssemblyCost = AssemblyCost
        self.AssemblyCarbon = AssemblyCarbon
        self.Layers = None

    def __hash__(self):
        return hash((self.__class__.__name__, self.Name, self.DataSource))

    def __eq__(self, other):
        if not isinstance(other, WindowConstruction):
            return False
        else:
            return all(
                [
                    self.Category == other.Category,
                    self.AssemblyCarbon == other.AssemblyCarbon,
                    self.AssemblyCost == other.AssemblyCost,
                    self.AssemblyEnergy == other.AssemblyEnergy,
                    self.DisassemblyCarbon == other.DisassemblyCarbon,
                    self.DisassemblyEnergy == other.DisassemblyEnergy,
                ]
            )

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
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
        """WindowConstruction from idf Construction Name.

        Example:
            >>> import archetypal as ar
            >>> idf = ar.load_idf("myidf")
            >>> construction_name = "Some construction name"
            >>> ar.WindowConstruction.from_epbunch(Name=construction_name,
            >>> idf=idf)

        Args:
            Construction (EpBunch): The Construction epbunch object.
            **kwargs: Other keywords passed to the constructor.
        """
        Name = Construction.Name
        idf = Construction.theidf
        wc = cls(Name=Name, idf=idf, **kwargs)
        wc.Layers = wc.layers()
        catdict = {1: "Single", 2: "Double", 3: "Triple", 4: "Quadruple"}
        wc.Category = catdict[
            len([lyr for lyr in wc.Layers if isinstance(lyr.Material, GlazingMaterial)])
        ]
        return wc

    def to_json(self):
        """Convert class properties to dict"""
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

    def layers(self):
        """Retrieve layers for the WindowConstruction"""
        c = self.idf.getobject("CONSTRUCTION", self.Name)
        layers = []
        for field in c.fieldnames:
            # Loop through the layers from the outside layer towards the
            # indoor layers and get the material they are made of.
            material = c.get_referenced_object(field)
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
                    # Todo: Make gas name generic, like in UmiTemplate Editor
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
                else:
                    continue

                layers.append(material_layer)
        return layers

    def combine(self, other, weights=None):
        """Append other to self. Return self + other as a new object. For
        now, simply returns self.

        todo:
            - Implement equivalent window layers for constant u-factor.

        """
        return self


class WindowType(IntEnum):
    External = 0
    Internal = 1


class WindowSetting(UmiBase, metaclass=Unique):
    """Window Settings define the various window-related properties of a
    specific :class:`Zone`. Control natural ventilation, shading and airflow
    networks and more using this class. This class serves the same role as the
    ZoneInformation>Windows tab in the UMI TemplateEditor.

    .. image:: ../images/template/zoneinfo-windows.png

    Classmethods:
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
        ShadingSystemType=0,
        Type=WindowType.External,
        IsZoneMixingOn=False,
        ZoneMixingAvailabilitySchedule=None,
        ZoneMixingDeltaTemperature=2,
        ZoneMixingFlowRate=0.001,
        **kwargs
    ):
        """Initialize a WindowSetting using default values:

        Args:
            Construction (WindowConstruction): The window construction.
            OperableArea (float): The operable window area as a ratio of total
                window area. eg. 0.8 := 80% of the windows area is operable.
            AfnWindowAvailability:
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
        self.ShadingSystemType = ShadingSystemType
        self.Type = Type  # Todo: Could be deprecated
        self.ZoneMixingDeltaTemperature = ZoneMixingDeltaTemperature
        self.ZoneMixingFlowRate = ZoneMixingFlowRate

    def __add__(self, other):
        return self.combine(other)

    def __repr__(self):
        v_ = [
            (k, v) for k, v in self.__dict__.items() if not isinstance(v, (dict, IDF))
        ]
        header = "{}: <{}>\n".format(self.Name, self.__class__.mro()[0].__name__)
        return header + tabulate.tabulate(v_, tablefmt="plain")

    def __str__(self):
        return repr(self)

    def __hash__(self):
        return hash((self.__class__.__name__, self.Name, self.DataSource))

    def __eq__(self, other):
        if not isinstance(other, WindowSetting):
            return False
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
    def generic(cls, idf):
        """Returns a generic window with SHGC=0.704, UFactor=2.703, Tvis=0.786

        Args:
            idf (IDF):
        """
        idf.add_object(
            "WindowMaterial:SimpleGlazingSystem".upper(),
            Name="SimpleWindow:SINGLE PANE HW WINDOW",
            UFactor=2.703,
            Solar_Heat_Gain_Coefficient=0.704,
            Visible_Transmittance=0.786,
            save=False,
        )

        constr = idf.add_object(
            "CONSTRUCTION",
            Name="SINGLE PANE HW WINDOW",
            Outside_Layer="SimpleWindow:SINGLE PANE HW WINDOW",
            save=False,
        )
        return cls.from_construction(Construction=constr)

    @classmethod
    def from_construction(cls, Construction, **kwargs):
        """Make a :class:`WindowSetting` directly from a Construction_ object.

        .. _Construction : https://bigladdersoftware.com/epx/docs/8-9/input
        -output-reference/group-surface-construction-elements.html
        #construction-000

        Examples:
            >>> import archetypal as ar
            >>> # Given an IDF object
            >>> idf = ar.load_idf("idfname")
            >>> construction = idf.getobject('CONSTRUCTION',
            >>>                              'AEDG-SmOffice 1A Window Fixed')
            >>> ar.WindowSetting.from_construction(Name='test_window',
            >>>                    Construction=construction)

        Args:
            Construction (EpBunch): The construction name for this window.
            **kwargs: Other keywords passed to the constructor.

        Returns:
            (windowSetting): The window setting object.
        """
        name = kwargs.pop("Name", Construction.Name + "_Window")
        kwargs["Name"] = name
        w = cls(idf=Construction.theidf, **kwargs)
        w.Construction = WindowConstruction.from_epbunch(Construction)
        w.AfnWindowAvailability = UmiSchedule.constant_schedule(idf=Construction.theidf)
        w.ShadingSystemAvailabilitySchedule = UmiSchedule.constant_schedule(
            idf=Construction.theidf
        )
        w.ZoneMixingAvailabilitySchedule = UmiSchedule.constant_schedule(
            idf=Construction.theidf
        )
        return w

    @classmethod
    def from_surface(cls, surface):
        """Build a WindowSetting object from a FenestrationSurface:Detailed_
        object. This constructor will detect common window constructions and
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
        if isinstance(surface, EpBunch) and not surface.Surface_Type.upper() == "DOOR":
            construction = surface.get_referenced_object("Construction_Name")
            construction = WindowConstruction.from_epbunch(construction)
            name = surface.Name
            shading_control = surface.get_referenced_object("Shading_Control_Name")
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
                    attr["ShadingSystemTransmittance"] = shade_mat[
                        "Visible_Transmittance"
                    ]
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
                            idf=surface.theidf, name="AlwaysOff", hourly_value=0
                        )
                    elif shade_ctrl_type.lower() == "alwayson":
                        attr[
                            "ShadingSystemAvailabilitySchedule"
                        ] = UmiSchedule.constant_schedule(idf=surface.theidf)
                    else:
                        log(
                            'Window "{}" uses a  window control type that '
                            'is not supported: "{}". Reverting to '
                            '"AlwaysOn"'.format(name, shade_ctrl_type),
                            lg.WARN,
                        )
                        attr[
                            "ShadingSystemAvailabilitySchedule"
                        ] = UmiSchedule.constant_schedule(idf=surface.theidf)
                # get shading type
                if shading_control["Shading_Type"] != "":
                    mapping = {
                        "InteriorShade": WindowType(1),
                        "ExteriorShade": WindowType(0),
                        "ExteriorScreen": WindowType(0),
                        "InteriorBlind": WindowType(1),
                        "ExteriorBlind": WindowType(0),
                        "BetweenGlassShade": WindowType(0),
                        "BetweenGlassBlind": WindowType(0),
                        "SwitchableGlazing": WindowType(0),
                    }
                    attr["ShadingSystemType"] = mapping[shading_control["Shading_Type"]]
            else:
                # Set default schedules
                attr[
                    "ShadingSystemAvailabilitySchedule"
                ] = UmiSchedule.constant_schedule(idf=surface.theidf)

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
                name = afn[
                    "Ventilation_Control_Zone_Temperature_Setpoint_Schedule_Name"
                ]
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
                        '"{}" is not fully supported. Rerverting to '
                        'defaults for object "{}"'.format(
                            leak.key, cls.mro()[0].__name__
                        ),
                        lg.WARNING,
                    )
                elif leak.key.upper() == "AIRFLOWNETWORK:MULTIZONE:SURFACE:CRACK":
                    log(
                        '"{}" is not fully supported. Rerverting to '
                        'defaults for object "{}"'.format(
                            leak.key, cls.mro()[0].__name__
                        ),
                        lg.WARNING,
                    )
                elif (
                    leak.key.upper()
                    == "AIRFLOWNETWORK:MULTIZONE:COMPONENT:DETAILEDOPENING"
                ):
                    log(
                        '"{}" is not fully supported. Rerverting to '
                        'defaults for object "{}"'.format(
                            leak.key, cls.mro()[0].__name__
                        ),
                        lg.WARNING,
                    )
                elif (
                    leak.key.upper()
                    == "AIRFLOWNETWORK:MULTIZONE:COMPONENT:ZONEEXHAUSTFAN"
                ):
                    log(
                        '"{}" is not fully supported. Rerverting to '
                        'defaults for object "{}"'.format(
                            leak.key, cls.mro()[0].__name__
                        ),
                        lg.WARNING,
                    )
                elif (
                    leak.key.upper()
                    == "AIRFLOWNETWORK:MULTIZONE:COMPONENT:SIMPLEOPENING"
                ):
                    log(
                        '"{}" is not fully supported. Rerverting to '
                        'defaults for object "{}"'.format(
                            leak.key, cls.mro()[0].__name__
                        ),
                        lg.WARNING,
                    )
            else:
                attr["AfnWindowAvailability"] = UmiSchedule.constant_schedule(
                    idf=surface.theidf
                )
            # Zone Mixing
            attr["ZoneMixingAvailabilitySchedule"] = UmiSchedule.constant_schedule(
                idf=surface.theidf
            )
            w = cls(
                Name=name,
                Construction=construction,
                idf=surface.theidf,
                Category=surface.theidf.building_name(use_idfname=True),
                **attr
            )
            return w

    @classmethod
    @timeit
    def from_zone(cls, zone):
        """Iterate over the zone subsurfaces and create a window object. If more
        than one window is created, use reduce to combine them together.

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
                    if subsurf.Surface_Type.lower() == "window":
                        window_sets.append(cls.from_surface(subsurf))

        if window_sets:
            # if one or more window has been created, reduce. Using reduce on
            # a len==1 list, will simply return the object.
            from operator import add

            return reduce(add, window_sets)
        else:
            # no window found, probably a core zone, return None.
            return None

    def combine(self, other, weights=None):
        """Append other to self. Return self + other as a new object.

        Args:
            other (WindowSetting): The other OpaqueMaterial object
            weights (list-like, optional): A list-like object of len 2. If None,
                equal weights are used.

        Returns:
            WindowSetting: A new combined object made of self + other.
        """
        if self is None:
            return other
        if other is None:
            return self
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
            Construction=self.Construction.combine(other.Construction, weights),
            AfnDischargeC=self._float_mean(other, "AfnDischargeC", weights),
            AfnTempSetpoint=self._float_mean(other, "AfnTempSetpoint", weights),
            AfnWindowAvailability=self.AfnWindowAvailability.combine(
                other.AfnWindowAvailability, weights),
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
            ShadingSystemType=self.ShadingSystemType
            if self.IsShadingSystemOn
            else other.ShadingSystemType,
            ZoneMixingDeltaTemperature=self._float_mean(
                other, "ZoneMixingDeltaTemperature", weights
            ),
            ZoneMixingFlowRate=self._float_mean(other, "ZoneMixingFlowRate", weights),
            ZoneMixingAvailabilitySchedule=self.ZoneMixingAvailabilitySchedule.combine(
                other.ZoneMixingAvailabilitySchedule, weights),
            ShadingSystemAvailabilitySchedule=self.ShadingSystemAvailabilitySchedule
                .combine(
                other.ShadingSystemAvailabilitySchedule, weights),
        )
        new_obj = self.__class__(**meta, **new_attr)
        new_obj._predecessors.extend(self._predecessors + other._predecessors)
        return new_obj

    def to_json(self):
        """Convert class properties to dict"""
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
        data_dict["ShadingSystemType"] = self.ShadingSystemType
        data_dict["Type"] = self.Type
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
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
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
