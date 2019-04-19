import collections

import numpy as np

from archetypal import settings, object_from_idfs, Schedule

created_obj = []


class Unique(type):

    def __call__(cls, *args, **kwargs):
        if kwargs['Name'] not in cls._cache:
            self = cls.__new__(cls, *args, **kwargs)
            cls.__init__(self, *args, **kwargs)
            cls._cache[kwargs['Name']] = self
            created_obj.append(self)
        return cls._cache[kwargs['Name']]

    def __init__(cls, name, bases, attributes):
        super().__init__(name, bases, attributes)
        cls._cache = {}


class UmiBase(object):
    def __init__(self, idf,
                 Name='unnamed',
                 Comments='',
                 DataSource=None,
                 **kwargs):
        self.idf = idf
        self.Comments = Comments
        if DataSource is None:
            self.DataSource = self.idf.building_name(use_idfname=True)
        else:
            self.DataSource = DataSource
        self.Name = Name
        self.all_objects = created_obj

    @property
    def id(self):
        return id(self)

    def __str__(self):
        """string representation of the object as id:Name"""
        return ':'.join([str(self.id), self.Name])

    def __repr__(self):
        return str(self)

    def to_json(self):
        return {"$id": "{}".format(self.id),
                "Name": "{}".format(self.Name)}
        # return {str(self.__class__.__name__): 'NotImplemented'}


class MaterialsGas(UmiBase, metaclass=Unique):
    """
    $id, Comments, Cost, DataSource, EmbodiedCarbon, EmbodiedCarbonStdDev,
    EmbodiedEnergy, EmbodiedEnergyStdDev, GasType, Life, Name,
    SubstitutionRatePattern, SubstitutionTimestep, TransportCarbon,
    TransportDistance, TransportEnergy, Type
    """

    def __init__(self, *args,
                 Cost=0,
                 EmbodiedCarbon=0,
                 EmbodiedCarbonStdDev=0,
                 EmbodiedEnergy=0,
                 EmbodiedEnergyStdDev=0,
                 Gas_Type=None,
                 Life=1,
                 SubstitutionRatePattern=[],
                 SubstitutionTimestep=0,
                 TransportCarbon=0,
                 TransportDistance=0,
                 TransportEnergy=0,
                 Type='Gas',
                 **kwargs):
        super(MaterialsGas, self).__init__(*args, **kwargs)

        self.cols_ = settings.common_umi_objects['GasMaterials']
        self.Cost = Cost
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedCarbonStdDev = EmbodiedCarbonStdDev
        self.EmbodiedEnergy = EmbodiedEnergy
        self.EmbodiedEnergyStdDev = EmbodiedEnergyStdDev
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.SubstitutionTimestep = SubstitutionTimestep
        self.TransportCarbon = TransportCarbon
        self.TransportDistance = TransportDistance
        self.TransportEnergy = TransportEnergy
        self.Life = Life
        self.Type = Type
        self.GasType = self._gas_type(Gas_Type)

        # TODO: What does Life mean? Always 1 in Boston UmiTemplate

    @staticmethod
    def _gas_type(Gas_Type):
        """Return the UMI gas type number

        Args:
            self (pandas.DataFrame):name

        Returns:
            int: UMI gas type number. The return number is specific to the
            umi api.

        """
        if 'air' in Gas_Type.lower():
            return 0
        elif 'argon' in Gas_Type.lower():
            return 1
        elif 'krypton' in Gas_Type.lower():
            return 2
        elif 'xenon' in Gas_Type.lower():
            return 3
        elif 'sf6' in Gas_Type.lower():
            return 4


class UmiSchedule(Schedule, UmiBase, metaclass=Unique):
    """
    $id, Category, Comments, DataSource, Name, Parts, Type
    """

    def __init__(self, Name, idf,
                 Category='Year',
                 **kwargs):
        super(UmiSchedule, self).__init__(idf=idf, sch_name=Name, **kwargs)

        self.Category = Category
        self.Type = self.schType
        self.Name = Name
        self._id = self.id
        self.develop()

    def __str__(self):
        """string representation of the object as id:Name"""
        return ':'.join([str(self.id), self.schName])

    def __repr__(self):
        return str(self)

    def __hash__(self):
        return hash(repr(self))

    def develop(self):
        year, weeks, days = self.to_year_week_day()

        newdays = []
        for day in days:
            newdays.append(
                DaySchedule(Name=day.Name, idf=self.idf, epbunch=day))
        newweeks = []
        for week in weeks:
            newweeks.append(WeekSchedule(Name=week.Name, idf=self.idf,
                                         epbunch=week, newdays=newdays))
        YearSchedule(Name=year.Name, _id=self.id, idf=self.idf, epbunch=year,
                     newweeks=newweeks,
                     Comments='Year Week Day schedules created from: '
                              '{}'.format(self.Name))


class YearSchedule(Schedule, metaclass=Unique):
    """$id, Category, Comments, DataSource, Name, Parts, Type
    """

    def __init__(self, Name, idf,
                 DataSource=None,
                 Category='Year',
                 **kwargs):
        super(YearSchedule, self).__init__(idf=idf, sch_name=Name, **kwargs)
        self.idf = idf
        self.Comments = kwargs.get('Comments', '')
        if DataSource is None:
            self.DataSource = self.idf.building_name(use_idfname=True)
        else:
            self.DataSource = DataSource
        self.Name = Name
        self.id = kwargs.get('_id', id(self))
        self.all_objects = created_obj

        self.Name = Name
        self.Category = Category
        self.Parts = self.get_parts()

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Year"
        data_dict["Parts"] = self.Parts
        data_dict["Type"] = self.schLimitType
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def get_parts(self):
        return [
            {
                "FromDay": 1,
                "FromMonth": 1,
                "ToDay": 31,
                "ToMonth": 12,
                "Schedule": {
                    "$ref": "112"
                }
            }
        ]


class WeekSchedule(Schedule, metaclass=Unique):
    """$id, Category, Comments, DataSource, Days, Name, Type"""

    def __init__(self, Name, idf,
                 DataSource=None,
                 Comments=None,
                 Category='Week',
                 **kwargs):
        super(WeekSchedule, self).__init__(idf=idf, sch_name=Name, **kwargs)
        self.idf = idf
        self.Comments = Comments
        if DataSource is None:
            self.DataSource = self.idf.building_name(use_idfname=True)
        else:
            self.DataSource = DataSource
        self.Name = Name
        self.all_objects = created_obj
        self.id = id(self)

        self.Name = Name
        self.Category = Category
        self.week = kwargs.get('week', None)
        self.Days = self.get_days()

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Week"
        data_dict["Days"] = self.Days
        data_dict["Type"] = self.schLimitType
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def get_days(self):
        return [
            {
                "$ref": "66"
            },
            {
                "$ref": "66"
            },
            {
                "$ref": "66"
            },
            {
                "$ref": "66"
            },
            {
                "$ref": "66"
            },
            {
                "$ref": "66"
            },
            {
                "$ref": "66"
            }
        ]


class DaySchedule(Schedule, metaclass=Unique):
    """$id, Category, Comments, DataSource, Name, Type, Values
    """

    def __init__(self, Name, idf,
                 DataSource=None,
                 Comments=None,
                 Category='Day',
                 **kwargs):
        super(DaySchedule, self).__init__(idf=idf, sch_name=Name, **kwargs)
        self.idf = idf
        self.Comments = Comments
        if DataSource is None:
            self.DataSource = self.idf.building_name(use_idfname=True)
        else:
            self.DataSource = DataSource
        self.Name = Name
        self.all_objects = created_obj
        self.id = id(self)

        self.Name = Name
        self.Category = Category
        self.Values = self.get_values()

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Day"
        data_dict["Type"] = self.schLimitType
        data_dict["Values"] = self.Values
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def get_values(self):
        return list(self.all_values.astype(float))


class BuildingTemplate(UmiBase, metaclass=Unique):
    """
    Category, Comments, Core.$ref, DataSource, Lifespan, Name,
    PartitionRatio, Perimeter.$ref, Structure.$ref
    """

    def __init__(self, *args,
                 Category='',
                 PartitionRatio=0.35,
                 Lifespan=60,
                 sql=None,
                 **kwargs):
        super(BuildingTemplate, self).__init__(*args, **kwargs)

        self.PartitionRatio = PartitionRatio
        self.Category = Category
        self.Lifespan = Lifespan
        self.sql = sql

        self.zone_refs()
        self.windows()

    def windows(self):
        """create windows"""
        surfaces = {}
        for zone in self.idf.idfobjects['ZONE']:
            for surface in zone.zonesurfaces:
                azimuth = str(round(surface.azimuth))
                if surface.tilt == 90.0:
                    surfaces[azimuth] = {'wall': 0,
                                         'window': 0,
                                         'wwr': 0}
                    surfaces[azimuth]['wall'] += surface.area
                    subs = surface.subsurfaces
                    surfaces[azimuth]['shading'] = {'noshading': True}
                    if subs:
                        for sub in subs:
                            surfaces[azimuth]['window'] += sub.area
                            surfaces[azimuth]['shading'] = \
                                self.get_shading_control(sub)
                    wwr = surfaces[azimuth]['window'] / surfaces[azimuth][
                        'wall']
                    surfaces[azimuth]['wwr'] = round(wwr, 1)

        self.Windows = [Window(Name='',
                               idf=self.idf,
                               **surfaces[azim]['shading']) for azim in
                        surfaces]

    def get_shading_control(self, sub):
        scn = sub.Shading_Control_Name
        obj = self.idf.getobject('WindowProperty:ShadingControl'.upper(), scn)
        if obj:
            sch_name = obj.Schedule_Name
            return {'IsShadingSystemOn': True,
                    'ShadingSystemType': 1,
                    'ShadingSystemSetPoint': obj.Setpoint,
                    'ShadingSystemAvailabilitySchedule': UmiSchedule(
                        Name=sch_name, idf=self.idf)}
        else:
            sch_name = list(self.idf.get_all_schedules(yearly_only=True))[0]
            return {'IsShadingSystemOn': False,
                    'ShadingSystemType': 0,
                    'ShadingSystemSetPoint': 0,
                    'ShadingSystemAvailabilitySchedule': UmiSchedule(
                        Name=sch_name, idf=self.idf)
                    }

    def zone_refs(self):
        """Recursively create the core and perimeter zones"""
        core_name = '_'.join([self.Name, 'core'])
        perim_name = '_'.join([self.Name, 'perim'])

        zone_info = zone_information(self.sql)
        zone_info['Type'] = zone_info.apply(iscore, axis=1)

        perim_n = zone_info.Type == 'Perimeter'
        core_n = zone_info.Type == 'Core'

        core_zone_names = zone_info.loc[core_n, 'Zone Name']
        perim_zone_names = zone_info.loc[perim_n, 'Zone Name']

        perim = Zone(Name=perim_name,
                     Zone_Names=perim_zone_names.values,
                     idf=self.idf,
                     sql=self.sql)

        if not core_zone_names.empty:
            # if there are core zones, create core zone
            core = Zone(Name=core_name,
                        Zone_Names=core_zone_names.values,
                        idf=self.idf,
                        sql=self.sql)
        else:
            # if there is no core, use the perim zone
            core = perim

        structure_name = '_'.join([self.Name, 'structure'])
        structure = StructureDefinition(Name=structure_name,
                                        idf=self.idf,
                                        sql=self.sql)

        self.Zones = [core, perim]

        self.Core = core
        self.Perimeter = perim
        self.Structure = structure

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["Core"] = {
            "$ref": str(self.Core.id)
        }
        data_dict["Lifespan"] = self.Lifespan
        data_dict["PartitionRatio"] = self.PartitionRatio
        data_dict["Perimeter"] = {
            "$ref": str(self.Perimeter.id)
        }
        data_dict["Structure"] = {
            "$ref": str(self.Structure.id)
        }
        data_dict["Windows"] = [win.to_json() for win in self.all_objects
                                if isinstance(win, Window)][0]
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


class StructureDefinition(UmiBase, metaclass=Unique):
    """
    $id, AssemblyCarbon, AssemblyCost, AssemblyEnergy, Category, Comments,
    DataSource, DisassemblyCarbon, DisassemblyEnergy, MassRatios, Name,
    """

    def __init__(self, *args,
                 AssemblyCarbon=0,
                 AssemblyCost=0,
                 AssemblyEnergy=0,
                 Category='',
                 DisassemblyCarbon=0,
                 DisassemblyEnergy=0,
                 MassRatios=0,
                 **kwargs):
        super(StructureDefinition, self).__init__(*args, **kwargs)
        self.AssemblyCarbon = AssemblyCarbon
        self.AssemblyCost = AssemblyCost
        self.AssemblyEnergy = AssemblyEnergy
        self.Category = Category
        self.DisassemblyCarbon = DisassemblyCarbon
        self.DisassemblyEnergy = DisassemblyEnergy
        self.MassRatios = MassRatios


class Zone(UmiBase, metaclass=Unique):
    """
    $id, Category, Comments, Conditioning.$ref, Constructions.$ref,
    DataSource, DaylightMeshResolution, DaylightWorkplaneHeight,
    DomesticHotWater.$ref, InternalMassConstruction.$ref,
    InternalMassExposedPerFloorArea, Loads.$ref, Name, Ventilation.$ref
    """

    def __init__(self, *args,
                 Zone_Names,
                 DaylightMeshResolution=1,
                 DaylightWorkplaneHeight=0.8,
                 InternalMassExposedPerFloorArea=1.05,
                 sql=None,
                 **kwargs):
        super(Zone, self).__init__(*args, **kwargs)
        self.Zone_Names = Zone_Names
        self.sql = sql
        self.conditioning()
        self.constructions()
        self.dhw()
        self.internal_mass_construction()
        self.InternalMassExposedPerFloorArea = InternalMassExposedPerFloorArea
        self.DaylightWorkplaneHeight = DaylightWorkplaneHeight
        self.DaylightMeshResolution = DaylightMeshResolution
        self.loads()

    def conditioning(self):
        """run conditioning and return id"""
        self.Conditioning_ref = []

    def constructions(self):
        """run construction sets and return id"""
        set_name = '_'.join([self.Name, 'constructions'])
        self.ConstructionsSet = ConstructionSet(Name=set_name,
                                                Zone_Names=self.Zone_Names,
                                                idf=self.idf,
                                                sql=self.sql)
        self.Constructions_ref = self.ConstructionsSet.id

    def dhw(self):
        """run domestic hot water and return id"""
        self.DomesticHotWater_ref = []

    def internal_mass_construction(self):
        """run internal mass construction and return id"""
        self.InternalMassConstruction_ref = []

    def loads(self):
        """run loads and return id"""
        self.Loads_ref = []


class ConstructionSet(UmiBase, metaclass=Unique):
    """Zone Specific Construction ids

    $id, Category, Comments, DataSource, Facade.$ref, Ground.$ref,
    IsFacadeAdiabatic, IsGroundAdiabatic, IsPartitionAdiabatic,
    IsRoofAdiabatic, IsSlabAdiabatic, Name, Partition.$ref, Roof.$ref, Slab.$ref
    """

    def __init__(self, *args,
                 Zone_Names,
                 sql=None,
                 **kwargs):
        super(ConstructionSet, self).__init__(*args, **kwargs)
        self.Zone_Names = Zone_Names
        self.sql = sql

        self.constructions()

    def constructions(self):
        """a copy of :func:``"""
        idfs = {self.Name: self.idf}

        constructions_df = object_from_idfs(idfs, 'CONSTRUCTION',
                                            first_occurrence_only=False)
        bldg_surface_detailed = object_from_idfs(idfs,
                                                 'BUILDINGSURFACE:DETAILED',
                                                 first_occurrence_only=False)
        constructions_df = bldg_surface_detailed.join(
            constructions_df.set_index(['Archetype', 'Name']),
            on=['Archetype', 'Construction_Name'], rsuffix='_constructions')
        constructions_df['Category'] = constructions_df.apply(
            lambda x: label_surface(x), axis=1)
        constructions_df['Type'] = constructions_df.apply(
            lambda x: type_surface(x),
            axis=1)
        constructions_df['Zone_Name'] = constructions_df[
            'Zone_Name'].str.upper()

        constructions_df = constructions_df[
            ~constructions_df.duplicated(subset=['Construction_Name'])]

        constructions_df['constructions'] = constructions_df.apply(
            lambda x: OpaqueConstruction(Name=x.Construction_Name,
                                         idf=self.idf,
                                         Category=x.Category,
                                         Type=x.Type),
            axis=1)

        partcond = (constructions_df.Type == 5) | (constructions_df.Type == 0)
        roofcond = constructions_df.Type == 1
        slabcond = (constructions_df.Type == 3) | (constructions_df.Type == 2)
        facadecond = constructions_df.Type == 0
        groundcond = constructions_df.Type == 2

        self.Partition = constructions_df.loc[partcond,
                                              'constructions'].values[0]
        self.Roof = constructions_df.loc[roofcond,
                                         'constructions'].values[0]
        self.Slab = constructions_df.loc[slabcond,
                                         'constructions'].values[0]
        self.Facade = constructions_df.loc[facadecond,
                                           'constructions'].values[0]
        self.Ground = constructions_df.loc[groundcond,
                                           'constructions'].values[0]


class OpaqueConstruction(UmiBase, metaclass=Unique):
    """$id, AssemblyCarbon, AssemblyCost, AssemblyEnergy, Category, Comments,
    DataSource, DisassemblyCarbon, DisassemblyEnergy, Layers, Name, Type
    """

    def __init__(self, *args,
                 AssemblyCarbon=0,
                 AssemblyCost=0,
                 AssemblyEnergy=0,
                 DisassemblyCarbon=0,
                 DisassemblyEnergy=0,
                 Type=0,
                 Category="Facade",
                 **kwargs):
        super(OpaqueConstruction, self).__init__(*args, **kwargs)
        self.Type = Type
        self.Category = Category
        self.AssemblyCarbon = AssemblyCarbon
        self.AssemblyCost = AssemblyCost
        self.AssemblyEnergy = AssemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.DisassemblyEnergy = DisassemblyEnergy

        self.Layers = self.layers()

    def layers(self):
        c = self.idf.getobject('CONSTRUCTION', self.Name)
        layers = []
        for layer in c.fieldvalues[2:]:
            material = self.idf.getobject('MATERIAL', layer)
            if material is None:
                material = self.idf.getobject('MATERIAL:NOMASS', layer)
                thickness = 0.0127
                conductivity = thickness / material.Thermal_Resistance
                specific_heat = 100
            else:
                thickness = material.Thickness
                conductivity = material.Conductivity
                specific_heat = material.Specific_Heat
            layers.append({'Material': OpaqueMaterial(Name=material.Name,
                                                      Roughness=material.Roughness,
                                                      SolarAbsorptance=material.Solar_Absorptance,
                                                      SpecificHeat=specific_heat,
                                                      Type='Material',
                                                      Conductivity=conductivity,
                                                      ThermalEmittance=material.Thermal_Absorptance,
                                                      VisibleAbsorptance=material.Visible_Absorptance,
                                                      idf=self.idf),
                           'Thickness': thickness})
        return layers

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Layers"] = [{"Material": {"$ref": str(lay['Material'].id)},
                                "Thickness": lay['Thickness']} for lay in
                               self.Layers]
        data_dict["Type"] = self.Type
        data_dict["AssemblyCarbon"] = self.AssemblyCarbon
        data_dict["AssemblyCost"] = self.AssemblyCost
        data_dict["AssemblyEnergy"] = self.AssemblyEnergy
        data_dict["DisassemblyCarbon"] = self.DisassemblyCarbon
        data_dict["DisassemblyEnergy"] = self.DisassemblyEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = str(self.DataSource)
        data_dict["Name"] = str(self.Name)

        return data_dict


class OpaqueMaterial(UmiBase, metaclass=Unique):
    """
    $id, Comments, Conductivity, Cost, DataSource, Density, EmbodiedCarbon,
    EmbodiedCarbonStdDev, EmbodiedEnergy, EmbodiedEnergyStdDev, Life,
    MoistureDiffusionResistance, Name, PhaseChange, PhaseChangeProperties,
    Roughness, SolarAbsorptance, SpecificHeat, SubstitutionRatePattern,
    SubstitutionTimestep, ThermalEmittance, TransportCarbon,
    TransportDistance, TransportEnergy, Type, VariableConductivity,
    VariableConductivityProperties, VisibleAbsorptance
    """

    def __init__(self, *args,
                 Conductivity,
                 Roughness,
                 SolarAbsorptance,
                 SpecificHeat,
                 Type,
                 ThermalEmittance,
                 VisibleAbsorptance,
                 VariableConductivity=False,
                 VariableConductivityProperties='',
                 TransportCarbon=0,
                 TransportDistance=0,
                 TransportEnergy=0,
                 SubstitutionRatePattern=[0.5, 1],
                 SubstitutionTimestep=20,
                 Cost=0,
                 Density=1,
                 EmbodiedCarbon=0.45,
                 EmbodiedCarbonStdDev=0,
                 EmbodiedEnergy=0,
                 EmbodiedEnergyStdDev=0,
                 Life=1,
                 MoistureDiffusionResistance=50,
                 PhaseChange=False,
                 PhaseChangeProperties='',
                 **kwargs):
        super(OpaqueMaterial, self).__init__(*args, **kwargs)


class Window(UmiBase, metaclass=Unique):
    """
    AfnDischargeC, AfnTempSetpoint, AfnWindowAvailability.$ref,
    Category, Comments, OpaqueConstruction.$ref, DataSource, IsShadingSystemOn,
    IsVirtualPartition, IsZoneMixingOn, Name, OperableArea,
    ShadingSystemAvailabilitySchedule.$ref, ShadingSystemSetpoint,
    ShadingSystemTransmittance, ShadingSystemType, Type,
    ZoneMixingAvailabilitySchedule.$ref, ZoneMixingDeltaTemperature,
    ZoneMixingFlowRate
    """

    def __init__(self, *args,
                 AfnDischargeC=0.65,
                 AfnTempSetpoint=20,
                 IsShadingSystemOn=False,
                 IsVirtualPartition=False,
                 IsZoneMixingOn=False,
                 OperableArea=0.8,
                 ShadingSystemSetpoint=350,
                 ShadingSystemTransmittance=0.5,
                 ShadingSystemType=0,
                 Type=0,
                 ZoneMixingDeltaTemperature=2,
                 ZoneMixingFlowRate=0.001,
                 Category='',
                 **kwargs):
        super(Window, self).__init__(*args, **kwargs)

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
        self.Category = Category

    def __add__(self, other):
        if isinstance(other, self.__class__):
            self.AfnDischargeC = max(self.AfnDischargeC, other.AfnDischargeC)
            self.AfnTempSetpoint = max(self.AfnTempSetpoint,
                                       other.AfnTempSetpoint)
            self.IsShadingSystemOn = any([self.IsShadingSystemOn,
                                          other.IsShadingSystemOn])
            self.IsVirtualPartition = any([self.IsVirtualPartition,
                                           other.IsVirtualPartition])
            self.IsZoneMixingOn = any([self.IsZoneMixingOn,
                                       other.IsZoneMixingOn])
            self.OperableArea = max(self.OperableArea,
                                    other.OperableArea)
            self.ShadingSystemSetpoint = max(self.ShadingSystemSetpoint,
                                             other.ShadingSystemSetpoint)
            self.ShadingSystemTransmittance = \
                max(self.ShadingSystemTransmittance,
                    other.ShadingSystemTransmittance)
            self.ShadingSystemType = self.ShadingSystemType
            self.Type = self.Type
            self.ZoneMixingDeltaTemperature = \
                max(self.ZoneMixingDeltaTemperature,
                    other.ZoneMixingDeltaTemperature)
            self.ZoneMixingFlowRate = max(self.ZoneMixingFlowRate,
                                          other.ZoneMixingFlowRate)
            self.Category = self.Category
            return self
        else:
            raise NotImplementedError

    def __iadd__(self, other):
        if isinstance(other, None):
            return self
        else:
            return self + other

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["AfnDischargeC"] = self.AfnDischargeC
        data_dict["AfnTempSetpoint"] = self.AfnTempSetpoint
        data_dict["AfnWindowAvailability"] = {
            "$ref": "145"
        }
        data_dict["Construction"] = {
            "$ref": "57"
        }
        data_dict["IsShadingSystemOn"] = self.IsShadingSystemOn
        data_dict["IsVirtualPartition"] = self.IsVirtualPartition
        data_dict["IsZoneMixingOn"] = self.IsZoneMixingOn
        data_dict["OperableArea"] = self.OperableArea
        data_dict["ShadingSystemAvailabilitySchedule"] = {
            "$ref": "145"
        }
        data_dict["ShadingSystemSetpoint"] = self.ShadingSystemSetpoint
        data_dict[
            "ShadingSystemTransmittance"] = self.ShadingSystemTransmittance
        data_dict["ShadingSystemType"] = self.ShadingSystemType
        data_dict["Type"] = self.Type
        data_dict["ZoneMixingAvailabilitySchedule"] = {
            "$ref": "145"
        }
        data_dict[
            "ZoneMixingDeltaTemperature"] = self.ZoneMixingDeltaTemperature,
        data_dict["ZoneMixingFlowRate"] = self.ZoneMixingFlowRate
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


# class WeekSchedules(UmiBase, metaclass=Unique):
#     """
#     $id, Category, Comments, DataSource, Name, Parts, Type
#     """
#
#     def __init__(self, *args,
#                  Category='Year',
#                  Parts=[],
#                  Type='Fraction',
#                  **kwargs):
#         super(WeekSchedules, self).__init__(*args, **kwargs)
#
#         self.cols_ = settings.common_umi_objects['WeekSchedules']
#         self.Category = Category
#         self.Parts = Parts
#         self.Type = Type
#         self.DataSource = self.Archetype
#
#
# class YearSchedules(UmiBase, metaclass=Unique):
#     """
#     $id, Category, Comments, DataSource, Name, Parts, Type
#     """
#
#     def __init__(self, *args,
#                  Category='Year',
#                  Parts=[],
#                  Type='Fraction',
#                  **kwargs):
#         super(YearSchedules, self).__init__(*args, **kwargs)
#
#         self.cols_ = settings.common_umi_objects['YearSchedules']
#         self.Category = Category
#         self.Parts = Parts
#         self.Type = Type
#         self.DataSource = self.Archetype


def label_surface(row):
    """
    Takes a boundary and returns its corresponding umi-Category

    Args:
        row:

    Returns:

    """
    # Floors
    if row['Surface_Type'] == 'Floor':
        if row['Outside_Boundary_Condition'] == 'Surface':
            return 'Interior Floor'
        if row['Outside_Boundary_Condition'] == 'Ground':
            return 'Ground Floor'
        if row['Outside_Boundary_Condition'] == 'Outdoors':
            return 'Exterior Floor'
        if row['Outside_Boundary_Condition'] == 'Adiabatic':
            return 'Interior Floor'
        else:
            return 'Other'

    # Roofs & Ceilings
    if row['Surface_Type'] == 'Roof':
        return 'Roof'
    if row['Surface_Type'] == 'Ceiling':
        return 'Interior Floor'
    # Walls
    if row['Surface_Type'] == 'Wall':
        if row['Outside_Boundary_Condition'] == 'Surface':
            return 'Partition'
        if row['Outside_Boundary_Condition'] == 'Outdoors':
            return 'Facade'
        if row['Outside_Boundary_Condition'] == 'Adiabatic':
            return 'Partition'
    return 'Other'


def type_surface(row):
    """
    Takes a boundary and returns its corresponding umi-type

    Args:
        row:

    Returns:
        str: The umi-type of boundary
    """

    # Floors
    if row['Surface_Type'] == 'Floor':
        if row['Outside_Boundary_Condition'] == 'Surface':
            return 3
        if row['Outside_Boundary_Condition'] == 'Ground':
            return 2
        if row['Outside_Boundary_Condition'] == 'Outdoors':
            return 4
        if row['Outside_Boundary_Condition'] == 'Adiabatic':
            return 5
        else:
            return np.NaN

    # Roofs & Ceilings
    if row['Surface_Type'] == 'Roof':
        return 1
    if row['Surface_Type'] == 'Ceiling':
        return 3
    # Walls
    if row['Surface_Type'] == 'Wall':
        if row['Outside_Boundary_Condition'] == 'Surface':
            return 5
        if row['Outside_Boundary_Condition'] == 'Outdoors':
            return 0
        if row['Outside_Boundary_Condition'] == 'Adiabatic':
            return 5
    return np.NaN


def zone_information(df):
    """Each zone_loads is summarized in a simple set of statements

    Args:
        df:

    Returns:
        df

    References:
        * `Zone Loads Information \
        <https://bigladdersoftware.com/epx/docs/8-3/output-details-and \
        -examples/eplusout.eio.html#zone_loads-information>`_

    """
    df = get_from_tabulardata(df)
    tbstr = df[(df.ReportName == 'Initialization Summary') &
               (df.TableName == 'Zone Information')].reset_index()
    # Ignore Zone that are not part of building area
    pivoted = tbstr.pivot_table(index=['RowName'],
                                columns='ColumnName',
                                values='Value',
                                aggfunc=lambda x: ' '.join(x))

    return pivoted.loc[pivoted['Part of Total Building Area'] == 'Yes', :]


def get_from_tabulardata(sql):
    """Returns a DataFrame from the 'TabularDataWithStrings' table.

    Args:
        sql (dict):

    Returns:
        (pandas.DataFrame)
    """
    tab_data_wstring = sql['TabularDataWithStrings']
    tab_data_wstring.index.names = ['Index']

    # strip whitespaces
    tab_data_wstring.Value = tab_data_wstring.Value.str.strip()
    tab_data_wstring.RowName = tab_data_wstring.RowName.str.strip()
    return tab_data_wstring


def iscore(row):
    """
    Helps to group by core and perimeter zones. If any of "has `core` in
    name" and "ExtGrossWallArea == 0" is true,
    will consider zone_loads as core, else as perimeter.

    Todo:
        * assumes a basement zone_loads will be considered as a core
          zone_loads since no ext wall area for basements.

    Args:
        row (pandas.Series): a row

    Returns:
        str: 'Core' or 'Perimeter'

    """
    if any(['core' in row['Zone Name'].lower(),
            float(row['Exterior Gross Wall Area {m2}']) == 0]):
        # We look for the string `core` in the Zone_Name
        return 'Core'
    elif row['Part of Total Building Area'] == 'No':
        return np.NaN
    elif 'plenum' in row['Zone Name'].lower():
        return np.NaN
    else:
        return 'Perimeter'
