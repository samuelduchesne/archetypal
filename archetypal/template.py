import collections

import eppy.modeleditor
import numpy as np

from archetypal import object_from_idfs, Schedule, calc_simple_glazing

created_obj = {}


class Unique(type):

    def __call__(cls, *args, **kwargs):
        if kwargs['Name'] not in created_obj:
            self = cls.__new__(cls, *args, **kwargs)
            cls.__init__(self, *args, **kwargs)
            cls._cache[kwargs['Name']] = self
            created_obj[kwargs['Name']] = self
        return created_obj[kwargs['Name']]

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
        self.Comments = ''
        if Comments != '':
            self.Comments += Comments
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
        """Convert class properties to dict"""
        return {"$id": "{}".format(self.id),
                "Name": "{}".format(self.Name)}
        # return {str(self.__class__.__name__): 'NotImplemented'}


class GasMaterial(UmiBase, metaclass=Unique):
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
        super(GasMaterial, self).__init__(*args, **kwargs)

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

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["GasType"] = self.GasType
        data_dict["Type"] = self.Type
        data_dict["EmbodiedEnergy"] = self.EmbodiedEnergy
        data_dict["EmbodiedEnergyStdDev"] = self.EmbodiedEnergyStdDev
        data_dict["EmbodiedCarbon"] = self.EmbodiedCarbon
        data_dict["EmbodiedCarbonStdDev"] = self.EmbodiedCarbonStdDev
        data_dict["Cost"] = self.Cost
        data_dict["Life"] = self.Life
        data_dict["SubstitutionRatePattern"] = self.SubstitutionRatePattern
        data_dict["SubstitutionTimestep"] = self.SubstitutionTimestep
        data_dict["TransportCarbon"] = self.TransportCarbon
        data_dict["TransportDistance"] = self.TransportDistance
        data_dict["TransportEnergy"] = self.TransportEnergy
        data_dict["Comment"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


class GlazingMaterial(UmiBase, metaclass=Unique):
    """$id, Comment, Conductivity, Cost, DataSource, Density, DirtFactor,
    EmbodiedCarbon, EmbodiedCarbonStdDev, EmbodiedEnergy,
    EmbodiedEnergyStdDev, IREmissivityBack, IREmissivityFront,
    IRTransmittance, Life, Name, Optical, OpticalData, SolarReflectanceBack,
    SolarReflectanceFront, SolarTransmittance, SubstitutionRatePattern,
    SubstitutionTimestep, TransportCarbon, TransportDistance,
    TransportEnergy, Type, VisibleReflectanceBack, VisibleReflectanceFront,
    VisibleTransmittance
    """

    def __init__(self, Density=2500, Conductivity=None, Optical=None,
                 OpticalData=None, SolarTransmittance=None,
                 SolarReflectanceFront=None, SolarReflectanceBack=None,
                 VisibleTransmittance=None, VisibleReflectanceFront=None,
                 VisibleReflectanceBack=None, IRTransmittance=None,
                 IREmissivityFront=None, IREmissivityBack=None, DirtFactor=1.0,
                 Type=None, EmbodiedEnergy=0, EmbodiedEnergyStdDev=0,
                 EmbodiedCarbon=0, EmbodiedCarbonStdDev=0, Cost=0.0, Life=1,
                 SubstitutionRatePattern=[0.2], SubstitutionTimestep=50,
                 TransportCarbon=None, TransportDistance=None,
                 TransportEnergy=0, *args, **kwargs):
        super(GlazingMaterial, self).__init__(*args, **kwargs)
        self.TransportEnergy = TransportEnergy
        self.TransportDistance = TransportDistance
        self.TransportCarbon = TransportCarbon
        self.SubstitutionTimestep = SubstitutionTimestep
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.Life = Life
        self.Cost = Cost
        self.EmbodiedCarbonStdDev = EmbodiedCarbonStdDev
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedEnergyStdDev = EmbodiedEnergyStdDev
        self.EmbodiedEnergy = EmbodiedEnergy
        self.Type = Type
        self.DirtFactor = DirtFactor
        self.IREmissivityBack = IREmissivityBack
        self.IREmissivityFront = IREmissivityFront
        self.IRTransmittance = IRTransmittance
        self.VisibleReflectanceBack = VisibleReflectanceBack
        self.VisibleReflectanceFront = VisibleReflectanceFront
        self.VisibleTransmittance = VisibleTransmittance
        self.SolarReflectanceBack = SolarReflectanceBack
        self.SolarReflectanceFront = SolarReflectanceFront
        self.SolarTransmittance = SolarTransmittance
        self.OpticalData = OpticalData
        self.Optical = Optical
        self.Density = Density
        self.Conductivity = Conductivity

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Conductivity"] = self.Conductivity
        data_dict["Density"] = self.Density
        data_dict["Optical"] = self.Optical
        data_dict["OpticalData"] = self.OpticalData
        data_dict["SolarTransmittance"] = self.SolarTransmittance
        data_dict["SolarReflectanceFront"] = self.SolarReflectanceFront
        data_dict["SolarReflectanceBack"] = self.SolarReflectanceBack
        data_dict["VisibleTransmittance"] = self.VisibleTransmittance
        data_dict["VisibleReflectanceFront"] = self.VisibleReflectanceFront
        data_dict["VisibleReflectanceBack"] = self.VisibleReflectanceBack
        data_dict["IRTransmittance"] = self.IRTransmittance
        data_dict["IREmissivityFront"] = self.IREmissivityFront
        data_dict["IREmissivityBack"] = self.IREmissivityBack
        data_dict["DirtFactor"] = self.DirtFactor
        data_dict["Type"] = self.Type
        data_dict["EmbodiedEnergy"] = self.EmbodiedEnergy
        data_dict["EmbodiedEnergyStdDev"] = self.EmbodiedEnergyStdDev
        data_dict["EmbodiedCarbon"] = self.EmbodiedCarbon
        data_dict["EmbodiedCarbonStdDev"] = self.EmbodiedCarbonStdDev
        data_dict["Cost"] = self.Cost
        data_dict["Life"] = self.Life
        data_dict["SubstitutionRatePattern"] = self.SubstitutionRatePattern
        data_dict["SubstitutionTimestep"] = self.SubstitutionTimestep
        data_dict["TransportCarbon"] = self.TransportCarbon
        data_dict["TransportDistance"] = self.TransportDistance
        data_dict["TransportEnergy"] = self.TransportEnergy
        data_dict["Comment"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


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
                DaySchedule(Name=day.Name, idf=self.idf, epbunch=day,
                            Comments='Year Week Day schedules created from: '
                                     '{}'.format(self.Name)))
        newweeks = []
        for week in weeks:
            newweeks.append(WeekSchedule(Name=week.Name, idf=self.idf,
                                         epbunch=week, newdays=newdays,
                                         Comments='Year Week Day schedules '
                                                  'created from: '
                                                  '{}'.format(self.Name)))
        YearSchedule(Name=year.Name, _id=self.id, idf=self.idf, epbunch=year,
                     newweeks=newweeks,
                     Comments='Year Week Day schedules created from: '
                              '{}'.format(self.Name))

    def to_json(self):
        """UmiSchedule does not implement the to_json method because it is
        not used when generating the json file. Only Year-Week- and
        DaySchedule classes are used"""
        pass


class YearSchedule(Schedule, metaclass=Unique):
    """$id, Category, Comments, DataSource, Name, Parts, Type
    """

    def __init__(self, Name, idf, _id,
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
        self.id = _id
        self.all_objects = created_obj

        self.Name = Name
        self.Category = Category
        self.epbunch = kwargs['epbunch']
        self.Type = self.schLimitType
        self.Parts = self.get_parts(self.epbunch)
        self.schLimitType = self.get_schedule_type_limits_name()

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Year"
        data_dict["Parts"] = self.Parts
        data_dict["Type"] = self.schLimitType
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def get_parts(self, epbunch):
        parts = []
        for i in range(int(len(epbunch.fieldvalues[3:]) / 5)):
            week_day_schedule_name = epbunch[
                'ScheduleWeek_Name_{}'.format(i + 1)]

            FromMonth = epbunch['Start_Month_{}'.format(i + 1)]
            ToMonth = epbunch['End_Month_{}'.format(i + 1)]
            FromDay = epbunch['Start_Day_{}'.format(i + 1)]
            ToDay = epbunch['End_Day_{}'.format(i + 1)]
            parts.append(
                {
                    "FromDay": FromDay,
                    "FromMonth": FromMonth,
                    "ToDay": ToDay,
                    "ToMonth": ToMonth,
                    "Schedule": {
                        "$ref": self.all_objects[week_day_schedule_name].id
                    }
                }
            )
        return parts


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
        self.Days = self.get_days(kwargs['epbunch'])
        self.schLimitType = self.get_schedule_type_limits_name()

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Week"
        data_dict["Days"] = self.Days
        data_dict["Type"] = self.schLimitType
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def get_days(self, epbunch):
        blocks = []
        dayname = ['Sunday', 'Monday', 'Tuesday', 'Wednesday',
                   'Thursday', 'Friday', 'Saturday']
        for day in dayname:
            week_day_schedule_name = epbunch[
                "{}_ScheduleDay_Name".format(day)]
            blocks.append(
                {
                    "$ref": self.all_objects[week_day_schedule_name].id
                }
            )

        return blocks


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
        self.schLimitType = self.get_schedule_type_limits_name()

    def to_json(self):
        """Convert class properties to dict"""
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
        # Todo: This routine fails to identify windows for some IDF files
        #  such as LargeHotel.
        surfaces = {}
        window = []
        for zone in self.idf.idfobjects['ZONE']:
            surfaces[zone.Name] = {}
            for surface in zone.zonesurfaces:
                try:
                    # Todo: The following is inside a try/except because it
                    #  will fail on ThermalMass objects.
                    azimuth = str(round(surface.azimuth))
                    if surface.tilt == 90.0:
                        surfaces[zone.Name][azimuth] = {'wall': 0,
                                                        'window': 0,
                                                        'wwr': 0}
                        surfaces[zone.Name][azimuth]['wall'] += surface.area
                        subs = surface.subsurfaces
                        surfaces[zone.Name][azimuth]['shading'] = {}
                        if subs:
                            for sub in subs:
                                surfaces[zone.Name][azimuth]['Name'] = sub.Name
                                surfaces[zone.Name][azimuth][
                                    'Construction_Name'] = \
                                    sub.Construction_Name
                                surfaces[zone.Name][azimuth][
                                    'window'] += sub.area
                                surfaces[zone.Name][azimuth]['shading'] = \
                                    self.get_shading_control(sub)
                        wwr = surfaces[zone.Name][azimuth]['window'] / \
                              surfaces[zone.Name][azimuth][
                                  'wall']
                        surfaces[zone.Name][azimuth]['wwr'] = round(wwr, 1)

                        if surfaces[zone.Name][azimuth]['window'] > 0:
                            window.append(
                                Window(idf=self.idf,
                                       Name=surfaces[zone.Name][azimuth][
                                           'Name'],
                                       **surfaces[zone.Name][azimuth][
                                           'shading'],
                                       Construction=
                                       surfaces[zone.Name][azimuth][
                                           'Construction_Name']
                                       )
                            )
                except:
                    pass

        # window = []
        # for azim in surfaces:
        #     try:
        #         if surfaces[azim]['window'] > 0:
        #             window.append(
        #                 Window(idf=self.idf,
        #                        **surfaces[azim]['shading'],
        #                        **surfaces[azim]['window_name'])
        #             )
        #     except:
        #         pass
        if window:
            self.Windows = window[0]
        else:
            # create fake window
            # Schedule:Constant,
            #   AlwaysOn,     !- Name
            #   On/Off,       !- Schedule Type Limits Name
            #   1.0;          !- Hourly Value
            #
            # ScheduleTypeLimits,
            #   On/Off,       !- Name
            #   0,            !- Lower Limit Value
            #   1,            !- Upper Limit Value
            #   DISCRETE,     !- Numeric Type
            #   Availability; !- Unit Type
            self.idf.add_object(ep_object='SCHEDULETYPELIMITS', save=False,
                                Name='On/Off', Lower_Limit_Value=0,
                                Upper_Limit_Value=1, Numeric_Type='DISCRETE',
                                Unit_Type='AVAILABILITY')
            sch_name = 'AlwaysOn'
            self.idf.add_object(ep_object='SCHEDULE:CONSTANT', save=False,
                                Name=sch_name,
                                Schedule_Type_Limits_Name='On/Off',
                                Hourly_Value=1.0)
            kwargs = {'IsShadingSystemOn': False,
                      'ShadingSystemType': 0,
                      'ShadingSystemSetPoint': 0,
                      'ShadingSystemAvailabilitySchedule': UmiSchedule(
                          Name=sch_name, idf=self.idf),
                      'AfnWindowAvailability': UmiSchedule(
                          Name=sch_name, idf=self.idf),
                      'ZoneMixingAvailabilitySchedule': UmiSchedule(
                          Name=sch_name, idf=self.idf),
                      }
            msg = '\nThis window was created using the constant schedule ' \
                  'On/Off of 1'
            # 2.716 , !-  U-Factor
            # 0.763 , !-  Solar Heat Gain Coefficient
            # 0.812 ; !-  Visible Transmittance
            sgl = calc_simple_glazing(0.763, 2.716, 0.812)

            glazing_name = 'Custom glazing material with SHGC {}, ' \
                           'u-value {} and t_vis {}'.format(0.763, 2.716, 0.812)
            GlazingMaterial(**sgl, Name=glazing_name, idf=self.idf)
            construction_name = 'Custom Fenestration with SHGC {}, ' \
                                'u-value {} and t_vis {}'.format(0.763, 2.716,
                                                                 0.812)
            # Construction
            # B_Dbl_Air_Cl,            !- Name
            # B_Glass_Clear_3_0.003_B_Dbl_Air_Cl,  !- Outside Layer
            self.idf.add_object(ep_object='CONSTRUCTION', save=False,
                                Name=construction_name,
                                Outside_Layer=construction_name)

            self.Windows = Window(Name='Random Window', Comments=msg,
                                  idf=self.idf, Construction=construction_name,
                                  **kwargs)

            # Todo: We should actually raise an error once this method is
            #  corrected. Use the error bellow
            # raise ValueError('Could not create a Window for '
            #                  'building {}'.format(self.DataSource))

    def get_shading_control(self, sub):
        scn = sub.Shading_Control_Name
        obj = self.idf.getobject('WindowProperty:ShadingControl'.upper(), scn)
        if obj:
            sch_name = obj.Schedule_Name
            return {'IsShadingSystemOn': True,
                    'ShadingSystemType': 1,
                    'ShadingSystemSetPoint': obj.Setpoint,
                    'ShadingSystemAvailabilitySchedule': UmiSchedule(
                        Name=sch_name, idf=self.idf),
                    'AfnWindowAvailability': UmiSchedule(
                        Name=sch_name, idf=self.idf),
                    'ZoneMixingAvailabilitySchedule': UmiSchedule(
                        Name=sch_name, idf=self.idf),
                    # Todo: Add WindowConstruction here
                    }
        else:
            sch_name = list(self.idf.get_all_schedules(yearly_only=True))[0]
            return {'IsShadingSystemOn': False,
                    'ShadingSystemType': 0,
                    'ShadingSystemSetPoint': 0,
                    'ShadingSystemAvailabilitySchedule': UmiSchedule(
                        Name=sch_name, idf=self.idf),
                    'AfnWindowAvailability': UmiSchedule(
                        Name=sch_name, idf=self.idf),
                    'ZoneMixingAvailabilitySchedule': UmiSchedule(
                        Name=sch_name, idf=self.idf),
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

        perim = Zone(Zone_Names=perim_zone_names.values, sql=self.sql,
                     Name=perim_name, idf=self.idf)

        if not core_zone_names.empty:
            # if there are core zones, create core zone
            core = Zone(Zone_Names=core_zone_names.values, sql=self.sql,
                        Name=core_name, idf=self.idf)
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
        """Convert class properties to dict"""
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
        data_dict["Windows"] = self.Windows.to_json()
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def __hash__(self):
        return hash(self.Name)


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

    def __init__(self, *args, Category=None, Zone_Names,
                 DaylightMeshResolution=1, DaylightWorkplaneHeight=0.8,
                 InternalMassExposedPerFloorArea=1.05, sql=None, **kwargs):
        super(Zone, self).__init__(*args, **kwargs)
        self.Category = Category
        self.Zone_Names = Zone_Names
        self.sql = sql
        self.InternalMassExposedPerFloorArea = InternalMassExposedPerFloorArea
        self.conditioning()
        self.constructions()
        self.dhw()
        self.internal_mass_construction()
        self.DaylightWorkplaneHeight = DaylightWorkplaneHeight
        self.DaylightMeshResolution = DaylightMeshResolution
        self.loads()

    def conditioning(self):
        """run conditioning and return id"""
        self.Conditioning = []

    def constructions(self):
        """run construction sets and return id"""
        set_name = '_'.join([self.Name, 'constructions'])
        self.ConstructionsSet = ZoneConstructionSet(Name=set_name,
                                                    Zone_Names=self.Zone_Names,
                                                    idf=self.idf,
                                                    sql=self.sql)

    def dhw(self):
        """run domestic hot water and return id"""
        self.DomesticHotWater = []

    def internal_mass_construction(self):
        """Group internal walls into a ThermalMass object for each Zones"""

        surfaces = {}
        for zone in self.idf.idfobjects['ZONE']:
            for surface in zone.zonesurfaces:
                if surface.fieldvalues[0] == 'InternalMass':
                    oc = OpaqueConstruction(Name=surface.Construction_Name,
                                            idf=self.idf,
                                            Surface_Type='Wall',
                                            Outside_Boundary_Condition='Outdoors',
                                            )
                    self.InternalMassConstruction = oc
                    pass
                else:
                    # Todo: Create Equivalent InternalMassConstruction from
                    #  partitions. For now, creating dummy InternalMass

                    #   InternalMass,
                    #     PerimInternalMass,       !- Name
                    #     B_Ret_Thm_0,             !- Construction Name
                    #     Perim,                   !- Zone Name
                    #     2.05864785735637;        !- Surface Area {m2}

                    existgin_cons = self.idf.idfobjects['CONSTRUCTION'][0]
                    new = self.idf.copyidfobject(existgin_cons)
                    internal_mass = '{}InternalMass'.format(zone.Name)
                    new.Name = internal_mass + '_construction'
                    self.idf.add_object(
                        ep_object='InternalMass'.upper(),
                        save=False, Name=internal_mass,
                        Construction_Name=new.Name,
                        Zone_Name=zone.Name,
                        Surface_Area=10
                    )
                    oc = OpaqueConstruction(Name=new.Name,
                                            idf=self.idf,
                                            Surface_Type='Wall',
                                            Outside_Boundary_Condition='Outdoors'
                                            )
                    self.InternalMassConstruction = oc
                    self.InternalMassExposedPerFloorArea = \
                        self.idf.getobject('INTERNALMASS',
                                           internal_mass).Surface_Area / \
                        eppy.modeleditor.zonearea(self.idf, zone.Name)

    def loads(self):
        """run loads and return id"""
        self.Loads = []

    def ventilation(self):
        self.Ventilation = []

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Conditioning"] = {
            "$ref": "NotImplementedYet"  # str(self.Conditioning.id)
        }
        data_dict["Constructions"] = {
            "$ref": "NotImplementedYet"  # str(self.ConstructionsSet.id)
        }
        data_dict["DaylightMeshResolution"] = self.DaylightMeshResolution
        data_dict["DaylightWorkplaneHeight"] = self.DaylightWorkplaneHeight
        data_dict["DomesticHotWater"] = {
            "$ref": "NotImplementedYet"  # str(self.DomesticHotWater.id)
        }
        data_dict["InternalMassConstruction"] = {
            "$ref": str(self.InternalMassConstruction.id)
        }
        data_dict[
            "InternalMassExposedPerFloorArea"] = \
            self.InternalMassExposedPerFloorArea
        data_dict["Loads"] = {
            "$ref": "NotImplementedYet"  # str(self.Loads.id)
        }
        data_dict["Ventilation"] = {
            "$ref": "NotImplementedYet"  # str(self.Ventilation.id)
        }
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


class ZoneConstructionSet(UmiBase, metaclass=Unique):
    """Zone Specific Construction ids

    $id, Category, Comments, DataSource, Facade.$ref, Ground.$ref,
    IsFacadeAdiabatic, IsGroundAdiabatic, IsPartitionAdiabatic,
    IsRoofAdiabatic, IsSlabAdiabatic, Name, Partition.$ref, Roof.$ref, Slab.$ref
    """

    def __init__(self, Zone_Names,
                 Category='',
                 IsSlabAdiabatic=False,
                 IsRoofAdiabatic=False,
                 IsPartitionAdiabatic=False,
                 IsGroundAdiabatic=False,
                 IsFacadeAdiabatic=False,
                 sql=None,
                 **kwargs):
        super(ZoneConstructionSet, self).__init__(**kwargs)
        self.Category = Category
        self.IsSlabAdiabatic = IsSlabAdiabatic
        self.IsRoofAdiabatic = IsRoofAdiabatic
        self.IsPartitionAdiabatic = IsPartitionAdiabatic
        self.IsGroundAdiabatic = IsGroundAdiabatic
        self.IsFacadeAdiabatic = IsFacadeAdiabatic
        self.Zone_Names = Zone_Names
        self.sql = sql

        self.constructions()

    def constructions(self):
        """G"""
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

        # Here we create OpaqueConstruction using a apply.
        constructions_df['constructions'] = constructions_df.apply(
            lambda x: OpaqueConstruction(Name=x.Construction_Name,
                                         idf=self.idf,
                                         Surface_Type=x.Surface_Type,
                                         Outside_Boundary_Condition=x.Outside_Boundary_Condition,
                                         Category=x.Category),
            axis=1)

        partcond = (constructions_df.Type == 5) | (constructions_df.Type == 0)
        roofcond = constructions_df.Type == 1
        slabcond = (constructions_df.Type == 3) | (constructions_df.Type == 2)
        facadecond = constructions_df.Type == 0
        groundcond = constructions_df.Type == 2

        self.Partition = constructions_df.loc[partcond,
                                              'constructions'].values[0]
        self.IsPartitionAdiabatic = self.Partition.IsAdiabatic

        self.Roof = constructions_df.loc[roofcond,
                                         'constructions'].values[0]
        self.IsRoofAdiabatic = self.Roof.IsAdiabatic

        self.Slab = constructions_df.loc[slabcond,
                                         'constructions'].values[0]
        self.IsPartitionAdiabatic = self.Slab.IsAdiabatic

        self.Facade = constructions_df.loc[facadecond,
                                           'constructions'].values[0]
        self.IsPartitionAdiabatic = self.Facade.IsAdiabatic

        self.Ground = constructions_df.loc[groundcond,
                                           'constructions'].values[0]
        self.IsPartitionAdiabatic = self.Ground.IsAdiabatic

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Facade"] = {
            "$ref": str(self.Facade.id)
        }
        data_dict["Ground"] = {
            "$ref": str(self.Ground.id)
        }
        data_dict["Partition"] = {
            "$ref": str(self.Partition.id)
        }
        data_dict["Roof"] = {
            "$ref": str(self.Roof.id)
        }
        data_dict["Slab"] = {
            "$ref": str(self.Slab.id)
        }
        data_dict["IsFacadeAdiabatic"] = self.IsFacadeAdiabatic
        data_dict["IsGroundAdiabatic"] = self.IsGroundAdiabatic
        data_dict["IsPartitionAdiabatic"] = self.IsPartitionAdiabatic
        data_dict["IsRoofAdiabatic"] = self.IsRoofAdiabatic
        data_dict["IsSlabAdiabatic"] = self.IsSlabAdiabatic
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


class OpaqueConstruction(UmiBase, metaclass=Unique):
    """$id, AssemblyCarbon, AssemblyCost, AssemblyEnergy, Category, Comments,
    DataSource, DisassemblyCarbon, DisassemblyEnergy, Layers, Name, Type
    """

    def __init__(self, Surface_Type,
                 Outside_Boundary_Condition,
                 *args,
                 AssemblyCarbon=0,
                 AssemblyCost=0,
                 AssemblyEnergy=0,
                 DisassemblyCarbon=0,
                 DisassemblyEnergy=0,
                 Type=0,
                 Category="Facade",
                 IsAdiabatic=False,
                 **kwargs):
        super(OpaqueConstruction, self).__init__(*args, **kwargs)
        self.Surface_Type = Surface_Type
        self.Outside_Boundary_Condition = Outside_Boundary_Condition
        self.IsAdiabatic = IsAdiabatic
        self.Type = Type
        self.Category = Category
        self.AssemblyCarbon = AssemblyCarbon
        self.AssemblyCost = AssemblyCost
        self.AssemblyEnergy = AssemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.DisassemblyEnergy = DisassemblyEnergy

        self.type_surface()
        self.Layers = self.layers()

    def layers(self):
        """Retrieve layers for the OpaqueConstruction"""
        c = self.idf.getobject('CONSTRUCTION', self.Name)
        layers = []
        for layer in c.fieldvalues[2:]:
            # Loop through the layers from the outside layer towards the
            # indoor layers and get the material they are made of.
            material = self.idf.getobject('MATERIAL', layer)
            if material is None:
                # if the material was not found, mostevidently means it is a
                # nomass layer.
                material = self.idf.getobject('MATERIAL:NOMASS', layer)

                # Nomass layers are not supported by umi. Create a fake half
                # inch thickness and calculate conductivity using the thermal
                # resistance.
                thickness = 0.0127  # half inch layer tickness
                conductivity = thickness / material.Thermal_Resistance
                specific_heat = 100  # The lowest possible value
            else:
                # This is a regular mass layer. Get its properties
                thickness = material.Thickness
                conductivity = material.Conductivity
                specific_heat = material.Specific_Heat

            # Create the OpaqueMaterial and append to the list of layers
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

    def type_surface(self):
        """Takes a boundary and returns its corresponding umi-type"""

        # Floors
        if self.Surface_Type == 'Floor':
            if self.Outside_Boundary_Condition == 'Surface':
                self.Type = 3  # umi defined
            if self.Outside_Boundary_Condition == 'Ground':
                self.Type = 2  # umi defined
            if self.Outside_Boundary_Condition == 'Outdoors':
                self.Type = 4  # umi defined
            if self.Outside_Boundary_Condition == 'Adiabatic':
                self.Type = 5  # umi defined
                self.IsAdiabatic = True
            else:
                return ValueError(
                    'Cannot find Construction Type for "{}"'.format(self))

        # Roofs & Ceilings
        elif self.Surface_Type == 'Roof':
            self.Type = 1  # umi defined
        elif self.Surface_Type == 'Ceiling':
            self.Type = 3  # umi defined
        # Walls
        elif self.Surface_Type == 'Wall':
            if self.Outside_Boundary_Condition == 'Surface':
                self.Type = 5  # umi defined
            if self.Outside_Boundary_Condition == 'Outdoors':
                self.Type = 0  # umi defined
            if self.Outside_Boundary_Condition == 'Adiabatic':
                self.Type = 5  # umi defined
                self.IsAdiabatic = True
        else:
            raise ValueError(
                'Cannot find Construction Type for "{}"'.format(self))

    def to_json(self):
        """Convert class properties to dict"""
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

        self.Conductivity = Conductivity
        self.Roughness = Roughness
        self.SolarAbsorptance = SolarAbsorptance
        self.SpecificHeat = SpecificHeat
        self.Type = Type
        self.ThermalEmittance = ThermalEmittance
        self.VisibleAbsorptance = VisibleAbsorptance
        self.VariableConductivity = VariableConductivity
        self.VariableConductivityProperties = VariableConductivityProperties
        self.TransportCarbon = TransportCarbon
        self.TransportDistance = TransportDistance
        self.TransportEnergy = TransportEnergy
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.SubstitutionTimestep = SubstitutionTimestep
        self.Cost = Cost
        self.Density = Density
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedCarbonStdDev = EmbodiedCarbonStdDev
        self.EmbodiedEnergy = EmbodiedEnergy
        self.EmbodiedEnergyStdDev = EmbodiedEnergyStdDev
        self.Life = Life
        self.MoistureDiffusionResistance = MoistureDiffusionResistance
        self.PhaseChange = PhaseChange
        self.PhaseChangeProperties = PhaseChangeProperties

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Conductivity"] = self.Conductivity
        data_dict["Density"] = self.Density
        data_dict["Roughness"] = self.Roughness
        data_dict["SpecificHeat"] = self.SpecificHeat
        data_dict["ThermalEmittance"] = self.ThermalEmittance
        data_dict["SolarAbsorptance"] = self.SolarAbsorptance
        data_dict["VisibleAbsorptance"] = self.VisibleAbsorptance
        data_dict[
            "MoistureDiffusionResistance"] = self.MoistureDiffusionResistance
        data_dict["PhaseChange"] = self.PhaseChange
        data_dict["PhaseChangeProperties"] = self.PhaseChangeProperties
        data_dict["VariableConductivity"] = self.VariableConductivity
        data_dict[
            "VariableConductivityProperties"] = \
            self.VariableConductivityProperties
        data_dict["Type"] = self.Type
        data_dict["EmbodiedEnergy"] = self.EmbodiedEnergy
        data_dict["EmbodiedEnergyStdDev"] = self.EmbodiedEnergyStdDev
        data_dict["EmbodiedCarbon"] = self.EmbodiedCarbon
        data_dict["EmbodiedCarbonStdDev"] = self.EmbodiedCarbonStdDev
        data_dict["Cost"] = self.Cost
        data_dict["Life"] = self.Life
        data_dict["SubstitutionRatePattern"] = self.SubstitutionRatePattern
        data_dict["SubstitutionTimestep"] = self.SubstitutionTimestep
        data_dict["TransportCarbon"] = self.TransportCarbon
        data_dict["TransportDistance"] = self.TransportDistance
        data_dict["TransportEnergy"] = self.TransportEnergy
        data_dict["Comment"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


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

    def __init__(self, Name, ZoneMixingAvailabilitySchedule,
                 AfnWindowAvailability,
                 ShadingSystemAvailabilitySchedule,
                 *args,
                 Construction=None,
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

        self.Name = Name
        self.ZoneMixingAvailabilitySchedule = ZoneMixingAvailabilitySchedule
        self.ShadingSystemAvailabilitySchedule = \
            ShadingSystemAvailabilitySchedule
        self.Construction = self.window_construction(Construction)
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
        self.Category = Category

    def window_construction(self, window_construction_name):
        window_construction = WindowConstruction(Name=window_construction_name,
                                                 idf=self.idf)

        return window_construction

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
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["AfnDischargeC"] = self.AfnDischargeC
        data_dict["AfnTempSetpoint"] = self.AfnTempSetpoint
        data_dict["AfnWindowAvailability"] = {
            "$ref": str(self.AfnWindowAvailability.id)
        }
        data_dict["Construction"] = {
            "$ref": str(self.Construction.id)
        }
        data_dict["IsShadingSystemOn"] = self.IsShadingSystemOn
        data_dict["IsVirtualPartition"] = self.IsVirtualPartition
        data_dict["IsZoneMixingOn"] = self.IsZoneMixingOn
        data_dict["OperableArea"] = self.OperableArea
        data_dict["ShadingSystemAvailabilitySchedule"] = {
            "$ref": str(self.ShadingSystemAvailabilitySchedule.id)
        }
        data_dict["ShadingSystemSetpoint"] = self.ShadingSystemSetpoint
        data_dict[
            "ShadingSystemTransmittance"] = self.ShadingSystemTransmittance
        data_dict["ShadingSystemType"] = self.ShadingSystemType
        data_dict["Type"] = self.Type
        data_dict["ZoneMixingAvailabilitySchedule"] = {
            "$ref": str(self.ZoneMixingAvailabilitySchedule.id)
        }
        data_dict[
            "ZoneMixingDeltaTemperature"] = self.ZoneMixingDeltaTemperature
        data_dict["ZoneMixingFlowRate"] = self.ZoneMixingFlowRate
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


class WindowConstruction(UmiBase, metaclass=Unique):
    """$id, AssemblyCarbon, AssemblyCost, AssemblyEnergy, Category, Comments,
    DataSource, DisassemblyCarbon, DisassemblyEnergy, Layers, Name, Type
    """

    def __init__(self, Type=None, AssemblyCarbon=0, AssemblyCost=0,
                 AssemblyEnergy=0, DisassemblyCarbon=0,
                 DisassemblyEnergy=0, Category=None,
                 *args, **kwargs):
        super(WindowConstruction, self).__init__(*args, **kwargs)
        self.Category = Category
        self.DisassemblyEnergy = DisassemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.AssemblyEnergy = AssemblyEnergy
        self.AssemblyCost = AssemblyCost
        self.AssemblyCarbon = AssemblyCarbon
        self.Type = Type
        self.Layers = self.layers()

    def to_json(self):
        """Convert class properties to dict"""
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
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def layers(self):
        """Retrieve layers for the WindowConstruction"""
        c = self.idf.getobject('CONSTRUCTION', self.Name)
        layers = []
        for field in c.fieldnames:
            # Loop through the layers from the outside layer towards the
            # indoor layers and get the material they are made of.
            material = c.get_referenced_object(field)
            if material:
                # Create the WindowMaterial:Glazing or the WindowMaterial:Gas
                # and append to the list of layers
                layers.append(
                    {
                        'Material': GlazingMaterial(
                            Name=material.Name,
                            Conductivity=material.Conductivity,
                            Optical=material.Optical_Data_Type,
                            OpticalData=material.Window_Glass_Spectral_Data_Set_Name,
                            SolarTransmittance=material
                                .Solar_Transmittance_at_Normal_Incidence,
                            SolarReflectanceFront=material
                                .Front_Side_Solar_Reflectance_at_Normal_Incidence,
                            SolarReflectanceBack=material
                                .Back_Side_Solar_Reflectance_at_Normal_Incidence,
                            VisibleTransmittance=material
                                .Visible_Transmittance_at_Normal_Incidence,
                            VisibleReflectanceFront=material
                                .Front_Side_Visible_Reflectance_at_Normal_Incidence,
                            VisibleReflectanceBack=material.Back_Side_Visible_Reflectance_at_Normal_Incidence,
                            IRTransmittance=material
                                .Infrared_Transmittance_at_Normal_Incidence,
                            IREmissivityFront=material
                                .Front_Side_Infrared_Hemispherical_Emissivity,
                            IREmissivityBack=material
                                .Back_Side_Infrared_Hemispherical_Emissivity,
                            DirtFactor=material.Dirt_Correction_Factor_for_Solar_and_Visible_Transmittance,
                            Type='Uncoated',
                            idf=self.idf
                        )
                        if material.obj[0].upper() ==
                           'WindowMaterial:Glazing'.upper()
                        else GasMaterial(Name=material.Name,
                                         idf=self.idf,
                                         Gas_Type=material.Gas_Type,
                                         ),
                        'Thickness': material.Thickness
                    }
                )
        return layers


def label_surface(row):
    """Takes a boundary and returns its corresponding umi-Category"""
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
    """Takes a boundary and returns its corresponding umi-type"""

    # Floors
    if row['Surface_Type'] == 'Floor':
        if row['Outside_Boundary_Condition'] == 'Surface':
            return 3  # umi defined
        if row['Outside_Boundary_Condition'] == 'Ground':
            return 2  # umi defined
        if row['Outside_Boundary_Condition'] == 'Outdoors':
            return 4  # umi defined
        if row['Outside_Boundary_Condition'] == 'Adiabatic':
            return 5
        else:
            return ValueError(
                'Cannot find Construction Type for "{}"'.format(row))

    # Roofs & Ceilings
    elif row['Surface_Type'] == 'Roof':
        return 1
    elif row['Surface_Type'] == 'Ceiling':
        return 3
    # Walls
    elif row['Surface_Type'] == 'Wall':
        if row['Outside_Boundary_Condition'] == 'Surface':
            return 5  # umi defined
        if row['Outside_Boundary_Condition'] == 'Outdoors':
            return 0  # umi defined
        if row['Outside_Boundary_Condition'] == 'Adiabatic':
            return 5  # umi defined
    else:
        raise ValueError('Cannot find Construction Type for "{}"'.format(row))


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
