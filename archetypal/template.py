################################################################################
# Module: template.py
# Description: Handles creation and conversion to and from UmiTemplate files
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import logging as lg
import random
import time
from enum import IntEnum

import eppy.modeleditor
import networkx
import numpy as np

from archetypal import object_from_idfs, Schedule, calc_simple_glazing, log, \
    save_and_show, IDF

created_obj = {}


class Unique(type):

    def __call__(cls, *args, **kwargs):
        key = (cls.mro()[0].__name__, kwargs['Name'])
        if key not in created_obj:
            self = cls.__new__(cls, *args, **kwargs)
            cls.__init__(self, *args, **kwargs)
            cls._cache[key] = self
            created_obj[key] = self
        return created_obj[key]

    def __init__(cls, name, bases, attributes):
        super().__init__(name, bases, attributes)
        cls._cache = {}


class UmiBase(object):
    def __init__(self,
                 Name,
                 idf=None,
                 Category='Uncategorized',
                 Comments=None,
                 DataSource=None,
                 sql=None,
                 **kwargs):
        """The UmiBase class handles common properties to all Template objects.

        Args:
            Name (str): Unique, the name of the object.
            idf (IDF): The idf object associated to this object.
            Category (str): Group objects by assigning the same category
                identifier. Thies can be any string.
            Comments (str): A comment displayed in the UmiTemplate.
            DataSource (str): A description of the datasource of the object.
                This helps identify from which data is the current object
                created.
            sql (dict of pandas.DataFrame):
        """
        super(UmiBase, self).__init__()
        self.Name = Name
        self.idf = idf
        self.sql = sql
        self.Category = Category
        self.Comments = ''
        try:
            self.Comments += Comments
        except:
            self.Comments = Comments
        if DataSource is None:
            try:
                self.DataSource = self.idf.building_name(use_idfname=True)
            except:
                self.DataSource = DataSource
        else:
            self.DataSource = DataSource
        self.all_objects = created_obj
        self.id = kwargs.get('$id', id(self))

    def __str__(self):
        """string representation of the object as id:Name"""
        return ':'.join([str(self.id), str(self.Name)])

    # def __repr__(self):
    #     return str(self)

    def to_json(self):
        """Convert class properties to dict"""
        return {"$id": "{}".format(self.id),
                "Name": "{}".format(self.Name)}

    def get_ref(self, ref):
        """Gets item matching ref id"""
        return [self.all_objects[obj]
                for obj in self.all_objects
                if self.all_objects[obj].id == ref['$ref']][0]

    def get_random_schedule(self):
        """Return a random YearSchedule from cache"""
        return random.choice([self.all_objects[obj] for obj in
                              self.all_objects if 'YearSchedule' in obj])

    def __hash__(self):
        return hash(self.Name)

    def to_dict(self):
        return {'$ref': str(self.id)}


class MaterialBase(UmiBase):
    def __init__(self, Name, Cost=0, EmbodiedCarbon=0, EmbodiedEnergy=0,
                 SubstitutionTimestep=0, TransportCarbon=0, TransportDistance=0,
                 TransportEnergy=0, SubstitutionRatePattern=None,
                 Conductivity=2.4, Density=2400,
                 **kwargs):
        super(MaterialBase, self).__init__(Name, **kwargs)
        if SubstitutionRatePattern is None:
            SubstitutionRatePattern = [1.0]
        self.Conductivity = Conductivity
        self.Cost = Cost
        self.Density = Density
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedEnergy = EmbodiedEnergy
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.SubstitutionTimestep = SubstitutionTimestep
        self.TransportCarbon = TransportCarbon
        self.TransportDistance = TransportDistance
        self.TransportEnergy = TransportEnergy

    def __eq__(self, other):
        if isinstance(other, MaterialBase):
            return \
                self.Name == other.Name and \
                self.Conductivity == other.Conductivity and \
                self.Cost == other.Cost and \
                self.Density == other.Density and \
                self.EmbodiedCarbon == other.EmbodiedCarbon and \
                self.EmbodiedEnergy == other.EmbodiedEnergy and \
                self.SubstitutionRatePattern == other.SubstitutionRatePattern \
                and \
                self.SubstitutionTimestep == other.SubstitutionTimestep and \
                self.TransportCarbon == other.TransportCarbon and \
                self.TransportDistance == other.TransportDistance and \
                self.TransportEnergy == other.TransportEnergy
        else:
            raise NotImplementedError

    def __hash__(self):
        return hash((self.Density,
                     self.EmbodiedCarbon,
                     self.EmbodiedEnergy,
                     ' '.join(map(str, self.SubstitutionRatePattern)),
                     self.SubstitutionTimestep,
                     self.TransportCarbon,
                     self.TransportDistance,
                     self.TransportEnergy))


class GasMaterial(MaterialBase, metaclass=Unique):
    """
    $id, Comments, Cost, DataSource, EmbodiedCarbon, EmbodiedCarbonStdDev,
    EmbodiedEnergy, EmbodiedEnergyStdDev, GasType, Life, Name,
    SubstitutionRatePattern, SubstitutionTimestep, TransportCarbon,
    TransportDistance, TransportEnergy, Type
    """

    def __init__(self, *args,
                 Category='Gases',
                 Type="Gas",
                 **kwargs):
        super(GasMaterial, self).__init__(*args, Category=Category, **kwargs)
        self.Type = Type

    @classmethod
    def from_json(cls, *args, **kwargs):
        gm = cls(*args, **kwargs)
        gas_type = kwargs.get('Name', None)
        gm.Type = gas_type

        return gm

    @classmethod
    def from_idf(cls, idf, *args, **kwargs):
        gms = idf.idfobjects['WindowMaterial:Gas'.upper()]
        # returns Idf_MSequence

        return [cls.from_ep_bunch(gm, *args, **kwargs) for gm in gms]

    @classmethod
    def from_ep_bunch(cls, ep_bunch, *args, **kwargs):
        """

        Args:
            ep_bunch (ep_bunch):
        """
        type = ep_bunch.Gas_Type
        name = ep_bunch.Name
        gm = cls(Type=type.upper(), Name=name)
        return gm

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = self.Category
        data_dict["Type"] = self.Type
        data_dict["Conductivity"] = self.Conductivity
        data_dict["Cost"] = self.Cost
        data_dict["Density"] = self.Density
        data_dict["EmbodiedCarbon"] = self.EmbodiedCarbon
        data_dict["EmbodiedEnergy"] = self.EmbodiedEnergy
        data_dict["SubstitutionRatePattern"] = self.SubstitutionRatePattern
        data_dict["SubstitutionTimestep"] = self.SubstitutionTimestep
        data_dict["TransportCarbon"] = self.TransportCarbon
        data_dict["TransportDistance"] = self.TransportDistance
        data_dict["TransportEnergy"] = self.TransportEnergy
        data_dict["Comments"] = self.Comments
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
        data_dict["DirtFactor"] = self.DirtFactor
        data_dict["IREmissivityBack"] = self.IREmissivityBack
        data_dict["IREmissivityFront"] = self.IREmissivityFront
        data_dict["IRTransmittance"] = self.IRTransmittance
        data_dict["SolarReflectanceBack"] = self.SolarReflectanceBack
        data_dict["SolarReflectanceFront"] = self.SolarReflectanceFront
        data_dict["SolarTransmittance"] = self.SolarTransmittance
        data_dict["VisibleReflectanceBack"] = self.VisibleReflectanceBack
        data_dict["VisibleReflectanceFront"] = self.VisibleReflectanceFront
        data_dict["VisibleTransmittance"] = self.VisibleTransmittance
        data_dict["Conductivity"] = self.Conductivity
        data_dict["Cost"] = self.Cost
        data_dict["Density"] = self.Density
        data_dict["EmbodiedCarbon"] = self.EmbodiedCarbon
        data_dict["EmbodiedEnergy"] = self.EmbodiedEnergy
        data_dict["SubstitutionRatePattern"] = self.SubstitutionRatePattern
        data_dict["SubstitutionTimestep"] = self.SubstitutionTimestep
        data_dict["TransportCarbon"] = self.TransportCarbon
        data_dict["TransportDistance"] = self.TransportDistance
        data_dict["TransportEnergy"] = self.TransportEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_idf(cls, idf, *args, **kwargs):
        glazms = idf.idfobjects['WindowMaterial:Glazing'.upper()]

        return [cls.from_ep_bunch(glazm, *args, **kwargs) for glazm in glazms]

    @classmethod
    def from_ep_bunch(cls, epbunch, *args, **kwargs):
        # Get parameter values from ep_bunch
        Name = epbunch.Name
        Density = 2500
        Conductivity = epbunch.Conductivity
        Optical = epbunch.Optical_Data_Type
        OpticalData = epbunch.Window_Glass_Spectral_Data_Set_Name
        SolarTransmittance = epbunch.Solar_Transmittance_at_Normal_Incidence
        SolarReflectanceFront = \
            epbunch.Front_Side_Solar_Reflectance_at_Normal_Incidence
        SolarReflectanceBack = \
            epbunch.Back_Side_Solar_Reflectance_at_Normal_Incidence
        VisibleTransmittance = epbunch.Visible_Transmittance_at_Normal_Incidence
        VisibleReflectanceFront = \
            epbunch.Front_Side_Visible_Reflectance_at_Normal_Incidence
        VisibleReflectanceBack = \
            epbunch.Back_Side_Visible_Reflectance_at_Normal_Incidence
        IRTransmittance = epbunch.Infrared_Transmittance_at_Normal_Incidence
        IREmissivityFront = epbunch.Front_Side_Infrared_Hemispherical_Emissivity
        IREmissivityBack = epbunch.Back_Side_Infrared_Hemispherical_Emissivity
        DirtFactor = \
            epbunch.Dirt_Correction_Factor_for_Solar_and_Visible_Transmittance
        Type = None
        EmbodiedEnergy = 0
        EmbodiedEnergyStdDev = 0
        EmbodiedCarbon = 0
        EmbodiedCarbonStdDev = 0
        Cost = 0.0
        Life = 1
        SubstitutionRatePattern = [0.2]
        SubstitutionTimestep = 50
        TransportCarbon = None
        TransportDistance = None
        TransportEnergy = 0

        return cls(Density, Conductivity, Optical,
                   OpticalData, SolarTransmittance,
                   SolarReflectanceFront, SolarReflectanceBack,
                   VisibleTransmittance, VisibleReflectanceFront,
                   VisibleReflectanceBack, IRTransmittance,
                   IREmissivityFront, IREmissivityBack, DirtFactor,
                   Type, EmbodiedEnergy, EmbodiedEnergyStdDev,
                   EmbodiedCarbon, EmbodiedCarbonStdDev, Cost, Life,
                   SubstitutionRatePattern, SubstitutionTimestep,
                   TransportCarbon, TransportDistance,
                   TransportEnergy, Name=Name, *args, **kwargs)


class UmiSchedule(Schedule, UmiBase, metaclass=Unique):
    """
    $id, Category, Comments, DataSource, Name, Parts, Type
    """

    def __init__(self, *args, **kwargs):
        """

        Args:
            *args:
            **kwargs:
        """
        kwargs['sch_name'] = kwargs.get('Name', None)
        super(UmiSchedule, self).__init__(*args, **kwargs)

        self.Type = self.schTypeLimitsName

    @classmethod
    def random_constant_schedule(cls, seed=1, **kwargs):
        randint = random.randint(25, 50)
        name = 'Constant_value_{}'.format(randint)
        random.seed(seed)

        sched = cls.constant_schedule(Name=name, **kwargs)
        sched = cls(Name=name, idf=sched.idf)
        return sched

    @classmethod
    def from_idf(cls, *args, **kwargs):
        sched = cls(*args, **kwargs)
        sched.develop()
        return sched

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
        year = YearSchedule(Name=year.Name, id=self.id, idf=self.idf,
                            epbunch=year,
                            newweeks=newweeks,
                            Comments='Year Week Day schedules created from: '
                                     '{}'.format(self.Name))
        return year

    def to_json(self):
        """UmiSchedule does not implement the to_json method because it is
        not used when generating the json file. Only Year-Week- and
        DaySchedule classes are used"""
        pass

    def to_dict(self):
        year_sched = self.develop()
        return year_sched.to_dict()


class YearScheduleParts():
    def __init__(self, FromDay=None, FromMonth=None, ToDay=None, ToMonth=None,
                 Schedule=None):
        self.FromDay = FromDay
        self.FromMonth = FromMonth
        self.ToDay = ToDay
        self.ToMonth = ToMonth
        self.Schedule = Schedule

    @classmethod
    def from_json(cls, all_objects, *args, **kwargs):
        ysp = cls(*args, **kwargs)
        ref = kwargs.get('Schedule', None)
        ysp.Schedule = all_objects.get_ref(ref)

        return ysp

    def to_dict(self):
        return collections.OrderedDict(FromDay=self.FromDay,
                                       FromMonth=self.FromMonth,
                                       ToDay=self.ToDay,
                                       ToMonth=self.ToMonth,
                                       Schedule={'$ref': str(self.Schedule.id)})

    def __str__(self):
        return str(self.to_dict())


class DaySchedule(UmiSchedule):
    """$id, Category, Comments, DataSource, Name, Type, Values
    """

    def __init__(self, *args, **kwargs):
        """

        Args:
            *args:
            **kwargs:
        """
        super(DaySchedule, self).__init__(*args, **kwargs)
        self.Values = kwargs.get('Values', None)

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Day"
        data_dict["Type"] = self.schTypeLimitsName
        data_dict["Values"] = self.Values
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def to_dict(self):
        return {'$ref': str(self.id)}


class WeekSchedule(UmiSchedule):
    """$id, Category, Comments, DataSource, Days, Name, Type"""

    def __init__(self, *args, **kwargs):
        """

        Args:
            *args:
            **kwargs:
        """
        super(WeekSchedule, self).__init__(*args, **kwargs)

        days = kwargs.get('Days', None)
        if days is None:
            self.Days = self.get_days(kwargs['epbunch'])
        else:
            self.Days = days
        _type = kwargs.get('Type', None)
        if type is None:
            self.schLimitType = self.get_schedule_type_limits_name()
        else:
            self.schLimitType = _type

    @classmethod
    def from_json(cls, *args, **kwargs):
        wc = cls(*args, **kwargs)
        days = kwargs.get('Days', None)
        wc.Days = [wc.get_ref(day) for day in days]
        return wc

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Week"
        day: DaySchedule
        data_dict["Days"] = [day.to_dict() for day in self.Days]
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
                    "$ref": self.all_objects[('DaySchedule',
                                              week_day_schedule_name)].id
                }
            )

        return blocks

    def to_dict(self):
        return {'$ref': str(self.id)}


class YearSchedule(UmiSchedule):
    """$id, Category, Comments, DataSource, Name, Parts, Type
    """

    def __init__(self, *args, **kwargs):
        """

        Args:
            *args:
            **kwargs:
        """
        super(YearSchedule, self).__init__(*args, **kwargs)
        self.Comments = kwargs.get('Comments', '')
        self.epbunch = kwargs.get('epbunch', None)
        type = kwargs.get('Type', None)
        if type is None:
            self.Type = self.schTypeLimitsName
        else:
            self.Type = type
        parts = kwargs.get('Parts', None)
        if parts is None:
            self.Parts = self.get_parts(self.epbunch)
        else:
            self.Parts = parts
        type = kwargs.get('Type', None)
        if type is None:
            self.schLimitType = self.get_schedule_type_limits_name()
        else:
            self.schLimitType = type

    @classmethod
    def from_json(cls, *args, **kwargs):
        ys = cls(*args, **kwargs)
        parts = kwargs.get('Parts', None)

        ys.Parts = [YearScheduleParts.from_json(all_objects=ys, **part) for
                    part in parts]

        return ys

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Year"
        data_dict["Parts"] = [part.to_dict() for part in self.Parts]
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
            parts.append(YearScheduleParts(FromDay, FromMonth, ToDay,
                                           ToMonth, self.all_objects[
                                               ('WeekSchedule',
                                                week_day_schedule_name)]))
        return parts

    def to_dict(self):
        return {'$ref': str(self.id)}


class DomesticHotWaterSetting(UmiBase, metaclass=Unique):
    """$id, Category, Comments, DataSource, FlowRatePerFloorArea, IsOn, Name,
    WaterSchedule.$ref, WaterSupplyTemperature, WaterTemperatureInlet
    """

    def __init__(self, WaterSchedule=None, *args,
                 Category=None, DataSource=None, FlowRatePerFloorArea=-0.03,
                 IsOn=True, WaterSupplyTemperature=65,
                 WaterTemperatureInlet=10, **kwargs):
        """

        Args:
            WaterSchedule (YearSchedule):
        """
        super(DomesticHotWaterSetting, self).__init__(*args, **kwargs)
        self.Category = Category
        self.DataSource = DataSource
        self.FlowRatePerFloorArea = FlowRatePerFloorArea
        self.IsOn = IsOn
        self.WaterSupplyTemperature = WaterSupplyTemperature
        self.WaterTemperatureInlet = WaterTemperatureInlet
        self.WaterSchedule = WaterSchedule

    @classmethod
    def from_json(cls, *args, **kwargs):
        dhws = cls(*args, **kwargs)
        wat_sch = kwargs.get('WaterSchedule', None)
        dhws.WaterSchedule = dhws.get_ref(wat_sch)
        return dhws

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["FlowRatePerFloorArea"] = self.FlowRatePerFloorArea
        data_dict["IsOn"] = self.IsOn
        data_dict["WaterSchedule"] = self.WaterSchedule.to_dict()
        data_dict["WaterSupplyTemperature"] = self.WaterSupplyTemperature
        data_dict["WaterTemperatureInlet"] = self.WaterTemperatureInlet
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


class VentilationSetting(UmiBase, metaclass=Unique):
    """$id, Afn, Infiltration, IsBuoyancyOn, IsInfiltrationOn, IsNatVentOn,
    IsScheduledVentilationOn, IsWindOn, NatVentMaxOutdoorAirTemp,
    NatVentMaxRelHumidity, NatVentMinOutdoorAirTemp, NatVentSchedule.$ref,
    NatVentZoneTempSetpoint, ScheduledVentilationAch,
    ScheduledVentilationSchedule.$ref, ScheduledVentilationSetpoint
    """

    def __init__(self, *args, NatVentSchedule=None,
                 ScheduledVentilationSchedule=None,
                 Afn=False, Infiltration=0.1, IsBuoyancyOn=True,
                 IsInfiltrationOn=True,
                 IsNatVentOn=False,
                 IsScheduledVentilationOn=False, IsWindOn=False,
                 NatVentMaxOutdoorAirTemp=30,
                 NatVentMaxRelHumidity=90, NatVentMinOutdoorAirTemp=0,
                 NatVentZoneTempSetpoint=18, ScheduledVentilationAch=0.6,
                 ScheduledVentilationSetpoint=18, **kwargs):
        super(VentilationSetting, self).__init__(*args, **kwargs)
        self.Afn = Afn
        self.Infiltration = Infiltration
        self.IsBuoyancyOn = IsBuoyancyOn
        self.IsInfiltrationOn = IsInfiltrationOn
        self.IsNatVentOn = IsNatVentOn
        self.IsScheduledVentilationOn = IsScheduledVentilationOn
        self.IsWindOn = IsWindOn
        self.NatVentMaxOutdoorAirTemp = NatVentMaxOutdoorAirTemp
        self.NatVentMaxRelHumidity = NatVentMaxRelHumidity
        self.NatVentMinOutdoorAirTemp = NatVentMinOutdoorAirTemp
        self.NatVentZoneTempSetpoint = NatVentZoneTempSetpoint
        self.ScheduledVentilationAch = ScheduledVentilationAch
        self.ScheduledVentilationSetpoint = ScheduledVentilationSetpoint

        self.ScheduledVentilationSchedule = ScheduledVentilationSchedule
        self.NatVentSchedule = NatVentSchedule

    @classmethod
    def from_json(cls, *args, **kwargs):
        vs = cls(*args, **kwargs)
        vent_sch = kwargs.get('ScheduledVentilationSchedule', None)
        vs.ScheduledVentilationSchedule = vs.get_ref(vent_sch)
        nat_sch = kwargs.get('NatVentSchedule', None)
        vs.NatVentSchedule = vs.get_ref(nat_sch)
        return vs

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Afn"] = self.Afn
        data_dict["IsBuoyancyOn"] = self.IsBuoyancyOn
        data_dict["Infiltration"] = self.Infiltration
        data_dict["IsInfiltrationOn"] = self.IsInfiltrationOn
        data_dict["IsNatVentOn"] = self.IsNatVentOn
        data_dict["IsScheduledVentilationOn"] = self.IsScheduledVentilationOn
        data_dict["NatVentMaxRelHumidity"] = self.NatVentMaxRelHumidity
        data_dict["NatVentMaxOutdoorAirTemp"] = self.NatVentMaxOutdoorAirTemp
        data_dict["NatVentMinOutdoorAirTemp"] = self.NatVentMinOutdoorAirTemp
        data_dict["NatVentSchedule"] = self.NatVentSchedule.to_dict()
        data_dict["NatVentZoneTempSetpoint"] = self.NatVentZoneTempSetpoint
        data_dict["ScheduledVentilationAch"] = self.ScheduledVentilationAch
        data_dict["ScheduledVentilationSchedule"] = \
            self.ScheduledVentilationSchedule.to_dict()
        data_dict["ScheduledVentilationSetpoint"] = \
            self.ScheduledVentilationSetpoint
        data_dict["IsWindOn"] = self.IsWindOn
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


class ZoneConditioning(UmiBase, metaclass=Unique):
    """$id, Category, Comments, CoolingCoeffOfPerf, CoolingLimitType,
    CoolingSchedule.$ref, CoolingSetpoint, DataSource, EconomizerType,
    HeatRecoveryEfficiencyLatent, HeatRecoveryEfficiencySensible,
    HeatRecoveryType, HeatingCoeffOfPerf, HeatingLimitType,
    HeatingSchedule.$ref, HeatingSetpoint, IsCoolingOn, IsHeatingOn,
    IsMechVentOn, MaxCoolFlow, MaxCoolingCapacity, MaxHeatFlow,
    MaxHeatingCapacity, MechVentSchedule.$ref, MinFreshAirPerArea,
    MinFreshAirPerPerson, Name"""

    def __init__(self, *args,
                 Category=None, Comments=None, CoolingCoeffOfPerf=None,
                 CoolingLimitType='NoLimit',
                 CoolingSetpoint=26, DataSource=None,
                 EconomizerType='NoEconomizer',
                 HeatRecoveryEfficiencyLatent=0.65,
                 HeatRecoveryEfficiencySensible=0.7,
                 HeatRecoveryType=None, HeatingCoeffOfPerf=None,
                 HeatingLimitType='NoLimit',
                 HeatingSetpoint=20, IsCoolingOn=True, IsHeatingOn=True,
                 IsMechVentOn=True, MaxCoolFlow=100, MaxCoolingCapacity=100,
                 MaxHeatFlow=100,
                 MaxHeatingCapacity=100,
                 MinFreshAirPerArea=0.001,
                 MinFreshAirPerPerson=0.001,
                 **kwargs):
        super(ZoneConditioning, self).__init__(*args, **kwargs)
        self.MechVentSchedule = None
        self.HeatingSchedule = None
        self.CoolingSchedule = None
        self.Category = Category
        self.Comments = Comments
        self.CoolingCoeffOfPerf = CoolingCoeffOfPerf
        self.CoolingLimitType = CoolingLimitType
        self.CoolingSetpoint = CoolingSetpoint
        self.DataSource = DataSource
        self.EconomizerType = EconomizerType
        self.HeatRecoveryEfficiencyLatent = HeatRecoveryEfficiencyLatent
        self.HeatRecoveryEfficiencySensible = HeatRecoveryEfficiencySensible
        self.HeatRecoveryType = HeatRecoveryType
        self.HeatingCoeffOfPerf = HeatingCoeffOfPerf
        self.HeatingLimitType = HeatingLimitType
        self.HeatingSetpoint = HeatingSetpoint
        self.IsCoolingOn = IsCoolingOn
        self.IsHeatingOn = IsHeatingOn
        self.IsMechVentOn = IsMechVentOn
        self.MaxCoolFlow = MaxCoolFlow
        self.MaxCoolingCapacity = MaxCoolingCapacity
        self.MaxHeatFlow = MaxHeatFlow
        self.MaxHeatingCapacity = MaxHeatingCapacity
        self.MinFreshAirPerArea = MinFreshAirPerArea
        self.MinFreshAirPerPerson = MinFreshAirPerPerson

    @classmethod
    def from_idf(cls, *args, **kwargs):
        zc = ZoneConditioning(*args, **kwargs)

        zc.MechVentSchedule = UmiSchedule.random_constant_schedule()
        zc.HeatingSchedule = UmiSchedule.random_constant_schedule()
        zc.CoolingSchedule = UmiSchedule.random_constant_schedule()
        return zc

    @classmethod
    def from_json(cls, *args, **kwargs):
        zc = cls(*args, **kwargs)

        cool_schd = kwargs.get('CoolingSchedule', None)
        zc.CoolingSchedule = zc.get_ref(cool_schd)
        heat_schd = kwargs.get('HeatingSchedule', None)
        zc.HeatingSchedule = zc.get_ref(heat_schd)
        mech_schd = kwargs.get('MechVentSchedule', None)
        zc.MechVentSchedule = zc.get_ref(mech_schd)
        return zc

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["CoolingSchedule"] = self.CoolingSchedule.to_dict()
        data_dict["CoolingCoeffOfPerf"] = self.CoolingCoeffOfPerf
        data_dict["CoolingSetpoint"] = self.CoolingSetpoint
        data_dict["CoolingLimitType"] = self.CoolingLimitType
        data_dict["EconomizerType"] = self.EconomizerType
        data_dict["HeatingCoeffOfPerf"] = self.HeatingCoeffOfPerf
        data_dict["HeatingLimitType"] = self.HeatingLimitType
        data_dict["HeatingSchedule"] = self.HeatingSchedule.to_dict()
        data_dict["HeatingSetpoint"] = self.HeatingSetpoint
        data_dict[
            "HeatRecoveryEfficiencyLatent"] = self.HeatRecoveryEfficiencyLatent
        data_dict[
            "HeatRecoveryEfficiencySensible"] = \
            self.HeatRecoveryEfficiencySensible
        data_dict["HeatRecoveryType"] = self.HeatRecoveryType
        data_dict["IsCoolingOn"] = self.IsCoolingOn
        data_dict["IsHeatingOn"] = self.IsHeatingOn
        data_dict["IsMechVentOn"] = self.IsMechVentOn
        data_dict["MaxCoolFlow"] = self.MaxCoolFlow
        data_dict["MaxCoolingCapacity"] = self.MaxCoolingCapacity
        data_dict["MaxHeatFlow"] = self.MaxHeatFlow
        data_dict["MaxHeatingCapacity"] = self.MaxHeatingCapacity
        data_dict["MechVentSchedule"] = self.MechVentSchedule.to_dict()
        data_dict["MinFreshAirPerArea"] = self.MinFreshAirPerArea
        data_dict["MinFreshAirPerPerson"] = self.MinFreshAirPerPerson
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


class ZoneLoad(UmiBase, metaclass=Unique):
    """$id, Category, Comments, DataSource, DimmingType,
    EquipmentAvailabilitySchedule.$ref, EquipmentPowerDensity,
    IlluminanceTarget, IsEquipmentOn, IsLightingOn, IsPeopleOn,
    LightingPowerDensity, LightsAvailabilitySchedule.$ref, Name,
    OccupancySchedule.$ref, PeopleDensity"""

    def __init__(self, *args,
                 DimmingType='Continuous',
                 EquipmentAvailabilitySchedule=None,
                 EquipmentPowerDensity=12,
                 IlluminanceTarget=500,
                 LightingPowerDensity=12,
                 LightsAvailabilitySchedule=None,
                 OccupancySchedule=None,
                 IsEquipmentOn=True,
                 IsLightingOn=True,
                 IsPeopleOn=True,
                 PeopleDensity=0.2,
                 **kwargs):
        super(ZoneLoad, self).__init__(*args, **kwargs)
        self.DimmingType = DimmingType
        self.EquipmentAvailabilitySchedule = EquipmentAvailabilitySchedule
        self.EquipmentPowerDensity = EquipmentPowerDensity
        self.IlluminanceTarget = IlluminanceTarget
        self.LightingPowerDensity = LightingPowerDensity
        self.LightsAvailabilitySchedule = LightsAvailabilitySchedule
        self.OccupancySchedule = OccupancySchedule
        self.IsEquipmentOn = IsEquipmentOn
        self.IsLightingOn = IsLightingOn
        self.IsPeopleOn = IsPeopleOn
        self.PeopleDensity = PeopleDensity

    @classmethod
    def from_json(cls, *args, **kwargs):
        zl = cls(*args, **kwargs)

        cool_schd = kwargs.get('EquipmentAvailabilitySchedule', None)
        zl.EquipmentAvailabilitySchedule = zl.get_ref(cool_schd)
        heat_schd = kwargs.get('LightsAvailabilitySchedule', None)
        zl.LightsAvailabilitySchedule = zl.get_ref(heat_schd)
        mech_schd = kwargs.get('OccupancySchedule', None)
        zl.OccupancySchedule = zl.get_ref(mech_schd)

        return zl

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["DimmingType"] = self.DimmingType
        data_dict["EquipmentAvailabilitySchedule"] = \
            self.EquipmentAvailabilitySchedule.to_dict()
        data_dict["EquipmentPowerDensity"] = self.EquipmentPowerDensity
        data_dict["IlluminanceTarget"] = self.IlluminanceTarget
        data_dict["LightingPowerDensity"] = self.LightingPowerDensity
        data_dict["LightsAvailabilitySchedule"] = \
            self.LightsAvailabilitySchedule.to_dict()
        data_dict["OccupancySchedule"] = self.OccupancySchedule.to_dict()
        data_dict["IsEquipmentOn"] = self.IsEquipmentOn
        data_dict["IsLightingOn"] = self.IsLightingOn
        data_dict["IsPeopleOn"] = self.IsPeopleOn
        data_dict["PeopleDensity"] = self.PeopleDensity
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


class BuildingTemplate(UmiBase, metaclass=Unique):
    """
    Category, Comments, Core.$ref, DataSource, Lifespan, Name,
    PartitionRatio, Perimeter.$ref, Structure.$ref
    """

    def __init__(self, *args,
                 Core=None,
                 Perimeter=None,
                 Structure=None,
                 Windows=None,
                 Lifespan=60,
                 PartitionRatio=0.35,
                 **kwargs):
        """

        Args:
            Structure (StructureDefinition, optional):
            Windows (WindowSetting, optional):
            Perimeter (Zone, optional):
            Core (Zone, optional)):
        """
        super(BuildingTemplate, self).__init__(*args, **kwargs)
        self._zone_graph = None
        self.Zones = None
        self.PartitionRatio = PartitionRatio
        self.Lifespan = Lifespan
        self.Core = Core
        self.Perimeter = Perimeter
        self.Structure = Structure
        self.Windows = Windows

    @property
    def zone_graph(self):
        """Create a graph representation of the building zones. An edge
        between two zones represents the adjacency of the two zones

        Returns:
            ZoneGraph: The building's zone graph object
        """
        if self._zone_graph is None:
            start_time = time.time()
            idf = self.idf

            G = ZoneGraph(name=idf.name)

            def is_core(this_zone):
                # if all surfaces don't have boundary condition == "Outdoors"
                return not any([True if s.Outside_Boundary_Condition.lower() ==
                                        'outdoors' else False for s in
                                this_zone.zonesurfaces])

            for zone in idf.idfobjects['ZONE']:

                G.add_node(zone.Name, epbunch=zone, core=is_core(zone))

                for surface in zone.zonesurfaces:
                    obco_name = surface.Outside_Boundary_Condition_Object
                    field_idd = surface.getfieldidd(
                        'Outside_Boundary_Condition_Object')
                    validobjects = field_idd['validobjects']

                    for key in validobjects:
                        obco_ = idf.getobject(key, obco_name)
                        if obco_:
                            epbunch = idf.getobject('ZONE', obco_.Zone_Name)
                            if epbunch:
                                G.add_node(epbunch.Name, epbunch=epbunch,
                                           core=is_core(epbunch))

                                G.add_edge(zone.Name, epbunch.Name,
                                           this_construction=surface.Construction_Name,
                                           their_construction=obco_.Construction_Name,
                                           is_different_construction=surface.Construction_Name != obco_.Construction_Name)
                                break
            log("Created zone graph in {:,.2f} seconds".format(
                time.time() - start_time))
            log(networkx.info(G), lg.DEBUG)
            self._zone_graph = G
        return self._zone_graph

    def view_building(self, fig_height=None, fig_width=6, plot_graph=False,
                      save=False, show=True, close=False, ax=None,
                      axis_off=False, cmap='plasma', dpi=300, file_format='png',
                      azim=-60, elev=30, filename=None, opacity=0.5,
                      proj_type='persp', **kwargs):
        """

        Args:
            fig_height (float): matplotlib figure height in inches.
            fig_width (float): matplotlib figure width in inches.
            plot_graph (bool): if True, add the graph plot to this plot.
            save (bool): if True, save the figure as an image file to disk.
            show (bool): if True, show the figure.
            close (bool): close the figure (only if show equals False) to
                prevent display.
            ax (matplotlib.axes._axes.Axes, optional): An existing axes
                object on which to plot this graph.
            axis_off (bool): If True, turn off the matplotlib axis.
            cmap (str): The name a registered
                :class:`matplotlib.colors.Colormap`.
            dpi (int): the resolution of the image file if saving.
            file_format (str): the format of the file to save (e.g., 'jpg',
                'png', 'svg', 'pdf')
            azim (float): Azimuthal viewing angle, defaults to -60.
            elev (float): Elevation viewing angle, defaults to 30.
            proj_type (str): Type of projection, accepts 'persp' and 'ortho'.
            filename (str): the name of the file if saving.
            opacity (float): 0.0 transparent through 1.0 opaque

        Returns:

        """
        from geomeppy.view_geometry import _get_collections, _get_limits
        from mpl_toolkits.mplot3d import Axes3D
        import matplotlib.pyplot as plt

        if fig_height is None:
            fig_height = fig_width

        if ax:
            fig = plt.gcf()
        else:
            fig = plt.figure(figsize=(fig_width, fig_height), dpi=dpi)
            ax = Axes3D(fig)

        collections = _get_collections(self.idf, opacity=opacity)
        for c in collections:
            ax.add_collection3d(c)

        # Set the initial view
        ax.view_init(elev, azim)
        ax.set_proj_type(proj_type)

        # calculate and set the axis limits
        limits = _get_limits(idf=self.idf)
        ax.set_xlim(limits["x"])
        ax.set_ylim(limits["y"])
        ax.set_zlim(limits["z"])

        if plot_graph:
            annotate = kwargs.get('annotate', False)
            self.zone_graph.plot_graph(ax=ax, annotate=annotate)

        fig, ax = save_and_show(fig=fig, ax=ax, save=save, show=show,
                                close=close, filename=filename,
                                file_format=file_format, dpi=dpi,
                                axis_off=axis_off, extent=None)
        return fig, ax

    @classmethod
    def from_json(cls, *args, **kwargs):
        bt = cls(*args, **kwargs)

        ref = kwargs.get('Core', None)
        bt.Core = bt.get_ref(ref)
        ref = kwargs.get('Perimeter', None)
        bt.Perimeter = bt.get_ref(ref)
        ref = kwargs.get('Structure', None)
        bt.Structure = bt.get_ref(ref)
        ref = kwargs.get('Windows', None)
        try:
            bt.Windows = WindowSetting.from_json(Name=ref.pop('Name'), **ref)
        except:
            bt.Windows = bt.get_ref(ref)

        return bt

    @classmethod
    def from_idf(cls, idf, **kwargs):
        name = idf.idfobjects['BUILDING'][0].Name
        core = None
        perimeter = None
        structure = None
        windows = None

        bt = cls(Core=core, Perimeter=perimeter, Structure=structure,
                 Windows=windows, Name=name, idf=idf, **kwargs)
        # G = bt.zone_graph
        return bt

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
                                surfaces[zone.Name][azimuth][
                                    'Name'] = surface.Name
                                surfaces[zone.Name][azimuth][
                                    'Construction_Name'] = \
                                    surface.Construction_Name
                                surfaces[zone.Name][azimuth][
                                    'window'] += surface.area
                                surfaces[zone.Name][azimuth]['shading'] = \
                                    self.get_shading_control(sub)
                        wwr = surfaces[zone.Name][azimuth]['window'] / \
                              surfaces[zone.Name][azimuth][
                                  'wall']
                        surfaces[zone.Name][azimuth]['wwr'] = round(wwr, 1)

                        if surfaces[zone.Name][azimuth]['window'] > 0:
                            window.append(
                                WindowSetting.from_idf(idf=self.idf,
                                                       Name=
                                                       surfaces[zone.Name][
                                                           azimuth][
                                                           'Name'],
                                                       **surfaces[zone.Name][
                                                           azimuth][
                                                           'shading'],
                                                       Construction=
                                                       surfaces[zone.Name][
                                                           azimuth][
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
        #                 WindowSetting(idf=self.idf,
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

            self.Windows = WindowSetting.from_idf(Name='Random WindowSetting',
                                                  Comments=msg,
                                                  idf=self.idf,
                                                  Construction=construction_name,
                                                  **kwargs)

            # Todo: We should actually raise an error once this method is
            #  corrected. Use the error bellow
            # raise ValueError('Could not create a WindowSetting for '
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

        perim = Zone.from_idf(Zone_Names=perim_zone_names.values, sql=self.sql,
                              Name=perim_name, idf=self.idf)

        if not core_zone_names.empty:
            # if there are core zones, create core zone
            core = Zone.from_idf(Zone_Names=core_zone_names.values,
                                 sql=self.sql,
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

        data_dict["Core"] = self.Core.to_dict()
        data_dict["Lifespan"] = self.Lifespan
        data_dict["PartitionRatio"] = self.PartitionRatio
        data_dict["Perimeter"] = self.Perimeter.to_dict()
        data_dict["Structure"] = self.Structure.to_dict()
        data_dict["Windows"] = self.Windows.to_dict()
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


class MassRatio(object):
    def __init__(self, HighLoadRatio=None, Material=None, NormalRatio=None):
        self.HighLoadRatio = HighLoadRatio
        self.Material = Material
        self.NormalRatio = NormalRatio

    def to_dict(self):
        """dict representation of object"""
        return collections.OrderedDict(HighLoadRatio=self.HighLoadRatio,
                                       Material={'$ref': str(
                                           self.Material.id)},
                                       NormalRatio=self.NormalRatio)


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
                 MassRatios=None,
                 **kwargs):
        super(StructureDefinition, self).__init__(*args, **kwargs)
        self.AssemblyCarbon = AssemblyCarbon
        self.AssemblyCost = AssemblyCost
        self.AssemblyEnergy = AssemblyEnergy
        self.Category = Category
        self.DisassemblyCarbon = DisassemblyCarbon
        self.DisassemblyEnergy = DisassemblyEnergy
        self.MassRatios = MassRatios

    @classmethod
    def from_json(cls, *args, **kwargs):
        sd = cls(*args, **kwargs)
        massratios = kwargs.get('MassRatios', None)
        sd.MassRatios = [MassRatio(HighLoadRatio=massratio['HighLoadRatio'],
                                   Material=sd.get_ref(massratio['Material']),
                                   NormalRatio=massratio['NormalRatio'])
                         for massratio in massratios]
        return sd

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["MassRatios"] = [mass.to_dict() for mass
                                   in self.MassRatios]
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


class Zone(UmiBase, metaclass=Unique):
    """
    $id, Category, Comments, Conditioning.$ref, Constructions.$ref,
    DataSource, DaylightMeshResolution, DaylightWorkplaneHeight,
    DomesticHotWater.$ref, InternalMassConstruction.$ref,
    InternalMassExposedPerFloorArea, Loads.$ref, Name, Ventilation.$ref
    """

    def __init__(self, *args, Conditioning=None, Constructions=None,
                 DomesticHotWater=None, Loads=None, Ventilation=None,
                 InternalMassConstruction=None,
                 DaylightMeshResolution=1, DaylightWorkplaneHeight=0.8,
                 InternalMassExposedPerFloorArea=1.05, **kwargs):
        """

        Args:
            Ventilation (VentilationSetting):
            Loads (ZoneLoad):
            InternalMassConstruction (OpaqueConstruction):
            DomesticHotWater (DomesticHotWaterSetting):
            Constructions (ZoneConstructionSet):
            Conditioning (ZoneConditioning):
        """
        super(Zone, self).__init__(*args, **kwargs)

        self.Ventilation = Ventilation
        self.Loads = Loads
        self.Conditioning = Conditioning
        self.Constructions = Constructions
        self.DaylightMeshResolution = DaylightMeshResolution
        self.DaylightWorkplaneHeight = DaylightWorkplaneHeight
        self.DomesticHotWater = DomesticHotWater
        self.InternalMassConstruction = InternalMassConstruction
        self.InternalMassExposedPerFloorArea = InternalMassExposedPerFloorArea

    @classmethod
    def from_ep_bunch(cls, zone):
        name = zone.Name
        zone_constructions = ZoneConstructionSet.from_epbunch(zone)
        z = cls(Name=name, Constructions=zone_constructions)

        return z

    @classmethod
    def from_idf(cls, *args, **kwargs):
        z = cls(*args, **kwargs)
        z.Zone_Names = kwargs.get('Zone_Names', None)
        z.sql = kwargs.get('sql', None)

        z.conditioning()
        z.constructions()
        z.ventilation()
        z.dhw()
        z.internal_mass_construction()
        z.loads()

        return z

    def conditioning(self):
        """run conditioning and return id"""
        self.Conditioning = ZoneConditioning.from_idf(Name=random.randint(1,
                                                                          999999))

    def constructions(self):
        """run construction sets and return id"""
        set_name = '_'.join([self.Name, 'constructions'])
        self.Constructions = ZoneConstructionSet.from_idf(
            Zone_Names=self.Zone_Names, sql=self.sql, Name=set_name,
            idf=self.idf)

    def dhw(self):
        """run domestic hot water and return id"""
        self.DomesticHotWater = DomesticHotWaterSetting(Name=str(
            random.randint(1, 999999)))

    def internal_mass_construction(self):
        """Group internal walls into a ThermalMass object for each Zones"""

        surfaces = {}
        for zone in self.idf.idfobjects['ZONE']:
            for surface in zone.zonesurfaces:
                if surface.fieldvalues[0] == 'InternalMass':
                    oc = OpaqueConstruction.from_idf(
                        Name=surface.Construction_Name,
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
                    oc = OpaqueConstruction.from_idf(Name=new.Name,
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
        self.Loads = ZoneLoad(Name=str(
            random.randint(1, 999999)))

    def ventilation(self):
        self.Ventilation = VentilationSetting(Name=str(
            random.randint(1, 999999)))

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Conditioning"] = self.Conditioning.to_dict()
        data_dict["Constructions"] = self.Constructions.to_dict()
        data_dict["DaylightMeshResolution"] = self.DaylightMeshResolution
        data_dict["DaylightWorkplaneHeight"] = self.DaylightWorkplaneHeight
        data_dict["DomesticHotWater"] = self.DomesticHotWater.to_dict()
        data_dict["InternalMassConstruction"] = \
            self.InternalMassConstruction.to_dict()
        data_dict[
            "InternalMassExposedPerFloorArea"] = \
            self.InternalMassExposedPerFloorArea
        data_dict["Loads"] = self.Loads.to_dict()
        data_dict["Ventilation"] = self.Ventilation.to_dict()
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_json(cls, *args, **kwargs):
        zone = cls(*args, **kwargs)

        ref = kwargs.get('Conditioning', None)
        zone.Conditioning = zone.get_ref(ref)
        ref = kwargs.get('Constructions', None)
        zone.Constructions = zone.get_ref(ref)
        ref = kwargs.get('DomesticHotWater', None)
        zone.DomesticHotWater = zone.get_ref(ref)
        ref = kwargs.get('InternalMassConstruction', None)
        zone.InternalMassConstruction = zone.get_ref(ref)
        ref = kwargs.get('Loads', None)
        zone.Loads = zone.get_ref(ref)
        ref = kwargs.get('Ventilation', None)
        zone.Ventilation = zone.get_ref(ref)

        return zone


class ZoneConstructionSet(UmiBase, metaclass=Unique):
    """Zone Specific Construction ids

    $id, Category, Comments, DataSource, Facade.$ref, Ground.$ref,
    IsFacadeAdiabatic, IsGroundAdiabatic, IsPartitionAdiabatic,
    IsRoofAdiabatic, IsSlabAdiabatic, Name, Partition.$ref, Roof.$ref,
    Slab.$ref
    """

    def __init__(self, *args, Zone_Names=None, Slab=None, IsSlabAdiabatic=False,
                 Roof=None, IsRoofAdiabatic=False, Partition=None,
                 IsPartitionAdiabatic=False, Ground=None,
                 IsGroundAdiabatic=False, Facade=None, IsFacadeAdiabatic=False,
                 **kwargs):
        """

        Args:
            Facade (OpaqueConstruction):
            Ground (OpaqueConstruction):
            Partition (OpaqueConstruction):
            Roof (OpaqueConstruction):
            Slab (OpaqueConstruction):

        """
        super(ZoneConstructionSet, self).__init__(*args, **kwargs)
        self.Slab = Slab
        self.IsSlabAdiabatic = IsSlabAdiabatic
        self.Roof = Roof
        self.IsRoofAdiabatic = IsRoofAdiabatic
        self.Partition = Partition
        self.IsPartitionAdiabatic = IsPartitionAdiabatic
        self.Ground = Ground
        self.IsGroundAdiabatic = IsGroundAdiabatic
        self.Facade = Facade
        self.IsFacadeAdiabatic = IsFacadeAdiabatic

        self.Zone_Names = Zone_Names

    @classmethod
    def from_json(cls, *args, **kwargs):
        zc = cls(*args, **kwargs)

        ref = kwargs.get('Facade', None)
        zc.Facade = zc.get_ref(ref)

        ref = kwargs.get('Ground', None)
        zc.Ground = zc.get_ref(ref)

        ref = kwargs.get('Partition', None)
        zc.Partition = zc.get_ref(ref)

        ref = kwargs.get('Roof', None)
        zc.Roof = zc.get_ref(ref)

        ref = kwargs.get('Slab', None)
        zc.Slab = zc.get_ref(ref)

        return zc

    @classmethod
    def from_idf(cls, *args, **kwargs):
        zc = cls(*args, **kwargs)

        zc.constructions()

        return zc

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
            lambda x: OpaqueConstruction.from_idf(Name=x.Construction_Name,
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

    @classmethod
    def from_epbunch(cls, zone):
        name = zone.Name
        # dispatch surfaces
        facade, ground, partition, roof, slab = [], [], [], [], []
        for surf in zone.zonesurfaces:
            for f, g, p, r, s in ZoneConstructionSet.dispath_surfaces(surf,
                                                                      zone):
                facade.append(f)
                ground.append(g)
                partition.append(p)
                roof.append(r)
                slab.append(s)
        z_set = cls(Facade=facade, Ground=ground, Partition=partition,
                    Roof=roof, Slab=slab, Name=name)
        return z_set

    @classmethod
    def dispath_surfaces(cls, surf, zone):
        dispatch = {
            ('Wall', 'Outdoors'): cls._do_facade,
            ('Floor', 'Ground'): cls._do_ground,
            ('Floor', 'Foundation'): cls._do_ground,
            ('Floor', 'Surface'): cls._do_slab,
            ('Floor', 'Adiabatic'): cls._do_slab,
            ('Wall', 'Adiabatic'): cls._do_partition,
            ('Wall', 'Surface'): cls._do_partition,
            ('Wall', 'Zone'): cls._do_partition,
            ('Wall', 'Ground'): cls._do_basement,
            ('Roof', 'Outdoors'): cls._do_roof,
            ('Ceiling', 'Adiabatic'): cls._do_slab,
            ('Ceiling', 'Surface'): cls._do_slab,
            ('Ceiling', 'Zone'): cls._do_slab,
        }
        a, b = surf.Surface_Type, surf.Outside_Boundary_Condition
        try:
            yield dispatch[a, b](surf), dispatch[a, b](surf), \
                  dispatch[a, b](surf), dispatch[a, b](surf), \
                  dispatch[a, b](surf)
        except KeyError as e:
            raise NotImplementedError(
                "surface '%s' in zone '%s' not supported by surface dispatcher "
                "with keys %s" % (surf.Name, zone.Name, e))

    @staticmethod
    def _do_facade(surf):
        log('surface "%s" assigned as a Facade' % surf.Name, lg.DEBUG)
        return OpaqueConstruction.from_epbunch(
            surf.theidf.getobject('Construction'.upper(),
                                  surf.Construction_Name))

    @staticmethod
    def _do_ground(surf):
        log('surface "%s" assigned as a Ground' % surf.Name, lg.DEBUG,
            name=surf.theidf.name)
        return OpaqueConstruction.from_epbunch(
            surf.theidf.getobject('Construction'.upper(),
                                  surf.Construction_Name))

    @staticmethod
    def _do_partition(surf):
        log('surface "%s" assigned as a Partition' % surf.Name, lg.DEBUG,
            name=surf.theidf.name)
        return OpaqueConstruction.from_epbunch(
            surf.theidf.getobject('Construction'.upper(),
                                  surf.Construction_Name))

    @staticmethod
    def _do_roof(surf):
        log('surface "%s" assigned as a Roof' % surf.Name, lg.DEBUG,
            name=surf.theidf.name)
        return OpaqueConstruction.from_epbunch(
            surf.theidf.getobject('Construction'.upper(),
                                  surf.Construction_Name))

    @staticmethod
    def _do_slab(surf):
        log('surface "%s" assigned as a Slab' % surf.Name, lg.DEBUG,
            name=surf.theidf.name)
        return OpaqueConstruction.from_epbunch(
            surf.theidf.getobject('Construction'.upper(),
                                  surf.Construction_Name))

    @staticmethod
    def _do_basement(surf):
        log('surface "%s" ignored because basement facades are not supported' %
            surf.Name, lg.WARNING,
            name=surf.theidf.name)


class ConstructionBase(UmiBase):
    def __init__(self, AssemblyCarbon=0, AssemblyCost=0, AssemblyEnergy=0,
                 DisassemblyCarbon=0, DisassemblyEnergy=0, *args, **kwargs):
        super(ConstructionBase, self).__init__(*args, **kwargs)
        self.AssemblyCarbon = AssemblyCarbon
        self.AssemblyCost = AssemblyCost
        self.AssemblyEnergy = AssemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.DisassemblyEnergy = DisassemblyEnergy


class LayeredConstruction(ConstructionBase):
    def __init__(self, *args, **kwargs):
        super(LayeredConstruction, self).__init__(*args, **kwargs)
        self.Layers = kwargs.get('Layers', None)


class MaterialLayer(object):
    def __init__(self, Material, Thickness):
        """

        Args:
            Material (OpaqueMaterial):
        """
        self.Thickness = Thickness
        self.Material = Material

    def to_dict(self):
        return collections.OrderedDict(Material={'$ref': str(self.Material.id)},
                                       Thickness=self.Thickness)


class OpaqueConstruction(LayeredConstruction, metaclass=Unique):
    """$id, AssemblyCarbon, AssemblyCost, AssemblyEnergy, Category, Comments,
    DataSource, DisassemblyCarbon, DisassemblyEnergy, Layers, Name, Type
    """

    def __init__(self,
                 *args,
                 Surface_Type=None,
                 Outside_Boundary_Condition=None,
                 IsAdiabatic=False,
                 **kwargs):
        super(OpaqueConstruction, self).__init__(*args, **kwargs)
        self.Surface_Type = Surface_Type
        self.Outside_Boundary_Condition = Outside_Boundary_Condition
        self.IsAdiabatic = IsAdiabatic

    @classmethod
    def from_json(cls, *args, **kwargs):
        oc = cls(*args, **kwargs)
        layers = kwargs.get('Layers', None)

        # resolve Material objects from ref
        oc.Layers = [MaterialLayer(oc.get_ref(layer['Material']),
                                   layer['Thickness'])
                     for layer in layers]
        return oc

    @classmethod
    def from_epbunch(cls, epbunch):
        # from the construction
        name = epbunch.Name
        c = cls(Name=name)
        c.Layers = c.layers(epbunch)
        return c

    @classmethod
    def from_idf(cls, *args, **kwargs):
        oc = cls(*args, **kwargs)
        c = oc.idf.getobject('CONSTRUCTION', oc.Name)
        oc.Layers = oc.layers(c)

        return oc

    @staticmethod
    def layers(c):
        """Retrieve layers for the OpaqueConstruction"""
        layers = []
        field_idd = c.getfieldidd('Outside_Layer')
        validobjects = field_idd['validobjects']  # plausible layer types
        for layer in c.fieldvalues[2:]:
            # Iterate over the constructions layers
            found = False
            for key in validobjects:
                try:
                    material = c.theidf.getobject(key, layer)
                    o = OpaqueMaterial.from_ep_bunch(material)
                    found = True
                except AttributeError:
                    pass
                else:
                    layers.append({'Material': o,
                                   'Thickness': o.Thickness})
            if not found:
                raise AttributeError("%s material not found in IDF" % layer)
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
        data_dict["Layers"] = [lay.to_dict() for lay in self.Layers]
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

    def __init__(self, Conductivity,
                 Roughness,
                 SolarAbsorptance,
                 SpecificHeat,
                 ThermalEmittance,
                 VisibleAbsorptance,
                 TransportCarbon=0,
                 TransportDistance=0,
                 TransportEnergy=0,
                 SubstitutionRatePattern=[0.5, 1],
                 SubstitutionTimestep=20,
                 Cost=0,
                 Density=1,
                 EmbodiedCarbon=0.45,
                 EmbodiedEnergy=0,
                 MoistureDiffusionResistance=50,
                 Thickness=None,
                 *args, **kwargs):
        super(OpaqueMaterial, self).__init__(*args, **kwargs)

        self.Conductivity = Conductivity
        self.Roughness = Roughness
        self.SolarAbsorptance = SolarAbsorptance
        self.SpecificHeat = SpecificHeat
        self.ThermalEmittance = ThermalEmittance
        self.VisibleAbsorptance = VisibleAbsorptance
        self.TransportCarbon = TransportCarbon
        self.TransportDistance = TransportDistance
        self.TransportEnergy = TransportEnergy
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.SubstitutionTimestep = SubstitutionTimestep
        self.Cost = Cost
        self.Density = Density
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedEnergy = EmbodiedEnergy
        self.MoistureDiffusionResistance = MoistureDiffusionResistance
        self.Thickness = Thickness

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict[
            "MoistureDiffusionResistance"] = self.MoistureDiffusionResistance
        data_dict["Roughness"] = self.Roughness
        data_dict["SolarAbsorptance"] = self.SolarAbsorptance
        data_dict["SpecificHeat"] = self.SpecificHeat
        data_dict["ThermalEmittance"] = self.ThermalEmittance
        data_dict["VisibleAbsorptance"] = self.VisibleAbsorptance
        data_dict["Conductivity"] = self.Conductivity
        data_dict["Cost"] = self.Cost
        data_dict["Density"] = self.Density
        data_dict["EmbodiedCarbon"] = self.EmbodiedCarbon
        data_dict["EmbodiedEnergy"] = self.EmbodiedEnergy
        data_dict["SubstitutionRatePattern"] = self.SubstitutionRatePattern
        data_dict["SubstitutionTimestep"] = self.SubstitutionTimestep
        data_dict["TransportCarbon"] = self.TransportCarbon
        data_dict["TransportDistance"] = self.TransportDistance
        data_dict["TransportEnergy"] = self.TransportEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_idf(cls, idf, *args, **kwargs):
        all_ = []
        all_.extend(idf.idfobjects['Material'.upper()])
        all_.extend(idf.idfobjects['Material:NoMass'.upper()])

        return [cls.from_ep_bunch(om, *args, **kwargs) for om in all_]

    @classmethod
    def from_ep_bunch(cls, epbunch, *args, **kwargs):
        if epbunch.key.upper() == 'MATERIAL':
            # do MATERIAL
            Name = epbunch.Name
            Conductivity = epbunch.Conductivity
            Roughness = epbunch.Roughness
            SolarAbsorptance = epbunch.Solar_Absorptance
            SpecificHeat = epbunch.Specific_Heat
            ThermalEmittance = epbunch.Thermal_Absorptance
            VisibleAbsorptance = epbunch.Visible_Absorptance
            Thickness = epbunch.Thickness
            return cls(Conductivity,
                       Roughness,
                       SolarAbsorptance,
                       SpecificHeat,
                       ThermalEmittance,
                       VisibleAbsorptance,
                       Thickness=Thickness,
                       Name=Name,
                       *args, **kwargs)
        elif epbunch.key.upper() == 'MATERIAL:NOMASS':
            # do MATERIAL:NOMASS
            Name = epbunch.Name
            Thickness = 0.0127  # half inch thickness
            Conductivity = Thickness / epbunch.Thermal_Resistance
            Roughness = epbunch.Roughness
            SolarAbsorptance = epbunch.Solar_Absorptance
            ThermalEmittance = epbunch.Thermal_Absorptance
            VisibleAbsorptance = epbunch.Visible_Absorptance
            Density = 1  # 1 kg/m3, smallest value umi allows
            SpecificHeat = 100  # 100 J/kg-K, smallest value umi allows
            return cls(Conductivity,
                       Roughness,
                       SolarAbsorptance,
                       SpecificHeat,
                       ThermalEmittance,
                       VisibleAbsorptance,
                       Thickness=Thickness,
                       Density=Density,
                       Name=Name,
                       *args, **kwargs)


class WindowType(IntEnum):
    External = 0
    Internal = 1


class WindowSetting(UmiBase, metaclass=Unique):
    """
    AfnDischargeC, AfnTempSetpoint, AfnWindowAvailability.$ref,
    Category, Comments, OpaqueConstruction.$ref, DataSource, IsShadingSystemOn,
    IsVirtualPartition, IsZoneMixingOn, Name, OperableArea,
    ShadingSystemAvailabilitySchedule.$ref, ShadingSystemSetpoint,
    ShadingSystemTransmittance, ShadingSystemType, Type,
    ZoneMixingAvailabilitySchedule.$ref, ZoneMixingDeltaTemperature,
    ZoneMixingFlowRate
    """

    def __init__(self, ZoneMixingAvailabilitySchedule, AfnWindowAvailability,
                 ShadingSystemAvailabilitySchedule, Construction, *args,
                 AfnDischargeC=0.65, AfnTempSetpoint=20,
                 IsShadingSystemOn=False, IsVirtualPartition=False,
                 IsZoneMixingOn=False, OperableArea=0.8,
                 ShadingSystemSetpoint=180, ShadingSystemTransmittance=0.5,
                 ShadingSystemType=0, Type=WindowType.External,
                 ZoneMixingDeltaTemperature=2,
                 ZoneMixingFlowRate=0.001, **kwargs):
        super(WindowSetting, self).__init__(*args, **kwargs)
        self.ZoneMixingAvailabilitySchedule = ZoneMixingAvailabilitySchedule
        self.ShadingSystemAvailabilitySchedule = \
            ShadingSystemAvailabilitySchedule
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

    @classmethod
    def from_idf(cls, *args, **kwargs):
        w = cls(*args, **kwargs)

        construction = kwargs.get('Construction', None)
        w.Construction = w.window_construction(construction)

        return w

    def window_construction(self, window_construction_name):
        window_construction = WindowConstruction.from_idf(
            Name=window_construction_name,
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
        data_dict["AfnWindowAvailability"] = \
            self.AfnWindowAvailability.to_dict()
        data_dict["Construction"] = {
            "$ref": str(self.Construction.id)
        }
        data_dict["IsShadingSystemOn"] = self.IsShadingSystemOn
        data_dict["IsVirtualPartition"] = self.IsVirtualPartition
        data_dict["IsZoneMixingOn"] = self.IsZoneMixingOn
        data_dict["OperableArea"] = self.OperableArea
        data_dict["ShadingSystemAvailabilitySchedule"] = \
            self.ShadingSystemAvailabilitySchedule.to_dict()
        data_dict["ShadingSystemSetpoint"] = self.ShadingSystemSetpoint
        data_dict[
            "ShadingSystemTransmittance"] = self.ShadingSystemTransmittance
        data_dict["ShadingSystemType"] = self.ShadingSystemType
        data_dict["Type"] = self.Type
        data_dict["ZoneMixingAvailabilitySchedule"] = \
            self.ZoneMixingAvailabilitySchedule.to_dict()
        data_dict[
            "ZoneMixingDeltaTemperature"] = self.ZoneMixingDeltaTemperature
        data_dict["ZoneMixingFlowRate"] = self.ZoneMixingFlowRate
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_json(cls, *args, **kwargs):
        w = cls(*args, **kwargs)

        ref = kwargs.get('AfnWindowAvailability', None)
        w.AfnWindowAvailability = w.get_ref(ref)
        ref = kwargs.get('Construction', None)
        w.Construction = w.get_ref(ref)
        ref = kwargs.get('ShadingSystemAvailabilitySchedule', None)
        w.ShadingSystemAvailabilitySchedule = w.get_ref(ref)
        ref = kwargs.get('ZoneMixingAvailabilitySchedule', None)
        w.ZoneMixingAvailabilitySchedule = w.get_ref(ref)
        return w


class WindowConstruction(UmiBase, metaclass=Unique):
    """$id, AssemblyCarbon, AssemblyCost, AssemblyEnergy, Category, Comments,
    DataSource, DisassemblyCarbon, DisassemblyEnergy, Layers, Name, Type
    """

    def __init__(self, AssemblyCarbon=0, AssemblyCost=0,
                 AssemblyEnergy=0, DisassemblyCarbon=0,
                 DisassemblyEnergy=0,
                 *args, **kwargs):
        super(WindowConstruction, self).__init__(*args, **kwargs)
        self.DisassemblyEnergy = DisassemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.AssemblyEnergy = AssemblyEnergy
        self.AssemblyCost = AssemblyCost
        self.AssemblyCarbon = AssemblyCarbon
        layers = kwargs.get('Layers', None)
        if layers is None:
            self.Layers = self.layers()
        else:
            self.Layers = layers

    @classmethod
    def from_json(cls, *args, **kwargs):
        wc = cls(*args, **kwargs)
        layers = kwargs.get('Layers', None)

        # resolve Material objects from ref
        wc.Layers = [MaterialLayer(wc.get_ref(layer['Material']),
                                   layer['Thickness'])
                     for layer in layers]
        return wc

    @classmethod
    def from_idf(cls, *args, **kwargs):
        wc = cls(*args, **kwargs)

        wc.Layers = wc.layers()

        return wc

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Layers"] = [layer.to_dict()
                               for layer in self.Layers]
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
                material_obj = GlazingMaterial(Name=material.Name,
                                               Conductivity=material.Conductivity,
                                               Optical=material.Optical_Data_Type,
                                               OpticalData=material.Window_Glass_Spectral_Data_Set_Name,
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
                                               Type='Uncoated', idf=self.idf) \
                    if \
                    material.obj[
                        0].upper() == 'WindowMaterial:Glazing'.upper() else \
                    GasMaterial(
                        Name=material.Name, idf=self.idf,
                        Gas_Type=material.Gas_Type)
                material_layer = MaterialLayer(material_obj, material.Thickness)
                layers.append(
                    material_layer
                )
        return layers


class ZoneGraph(networkx.Graph):
    """
    Base class for undirected graphs.

    A Graph stores nodes and edges with optional data, or attributes.

    Graphs hold undirected edges.  Self loops are allowed but multiple
    (parallel) edges are not.

    Nodes can be arbitrary (hashable) Python objects with optional
    key/value attributes. By convention `None` is not used as a node.

    Edges are represented as links between nodes with optional
    key/value attributes.
    """

    def __init__(self, incoming_graph_data=None, **attr):
        """Initialize a graph with edges, name, or graph attributes.

        Wrapper around the :class:`networkx.classes.graph.Graph` class.

        Args:
            incoming_graph_data : input graph (optional, default: None)
                Data to initialize graph. If None (default) an empty graph is
                created.  The data can be an edge list, or any NetworkX graph
                object.  If the corresponding optional Python packages are
                installed the data can also be a NumPy matrix or 2d ndarray,
                a SciPy sparse matrix, or a PyGraphviz graph.
            attr : keyword arguments, optional (default= no attributes)
                Attributes to add to graph as key=value pairs.
        """
        super(ZoneGraph, self).__init__(incoming_graph_data=incoming_graph_data,
                                        **attr)

    def plot_graph(self, fig_height=None, fig_width=6, save=False, show=True,
                   close=False, ax=None, axis_off=False, cmap='plasma', dpi=300,
                   file_format='png', azim=-60, elev=30, proj_type='persp',
                   filename=None, annotate=False, plt_style='ggplot'):
        """Plot the :class:`archetypal.template.ZoneGraph` in a 3D plot.

        The size of the node is relative to its
        :func:`networkx.Graph.degree`. The node degree is the number of edges
        adjacent to the node.

        The nodes are positioned in 3d space according to the mean value of
        the surfaces centroids. For concave volumes, this corresponds to the
        center of gravity of the volume. Some weird positioning can occur for
        convex volumes.

        Args:
            fig_height (float): matplotlib figure height in inches.
            fig_width (float): matplotlib figure width in inches.
            save (bool): if True, save the figure as an image file to disk.
            show (bool): if True, show the figure.
            close (bool): close the figure (only if show equals False) to
                prevent display.
            ax (matplotlib.axes._axes.Axes, optional): An existing axes
                object on which to plot this graph.
            axis_off (bool): If True, turn off the matplotlib axis.
            cmap (str): The name a registered
                :class:`matplotlib.colors.Colormap`.
            dpi (int): the resolution of the image file if saving.
            file_format (str): the format of the file to save (e.g., 'jpg',
                'png', 'svg', 'pdf')
            azim (float): Azimuthal viewing angle, defaults to -60.
            elev (float): Elevation viewing angle, defaults to 30.
            proj_type (str): Type of projection, accepts 'persp' and 'ortho'.
            filename (str): the name of the file if saving.
            annotate (bool or str): If True, annotates the node with the
                Zone Name. Pass a field_name to retrieve data from the
                epbunch of the zone.
            plt_style (str, dict, or list): A style specification. Valid
                options are:
                - str: The name of a style or a path/URL to a style file.
                For a list of available style names,
                see `style.available`.
                - dict: Dictionary with valid key/value pairs for
                :attr:`matplotlib.rcParams`.
                - list: A list of style specifiers (str or dict) applied from
                first to last in the list.

        Returns:
            fig, ax: fig, ax

        """
        from mpl_toolkits.mplot3d import Axes3D
        import matplotlib.pyplot as plt
        import numpy as np

        def avg(zone):
            X, Y, Z, dem = 0, 0, 0, 0
            from geomeppy.geom.polygons import Polygon3D, Vector3D
            from geomeppy.recipes import translate_coords

            ggr = zone.theidf.idfobjects["GLOBALGEOMETRYRULES"][0]

            for surface in zone.zonesurfaces:
                dem += 1
                if ggr.Coordinate_System.lower() == 'relative':
                    zone = zone.theidf.getobject('ZONE', surface.Zone_Name)
                    poly3d = Polygon3D(surface.coords)
                    origin = (zone.X_Origin, zone.Y_Origin, zone.Z_Origin)
                    coords = translate_coords(poly3d, Vector3D(*origin))
                    poly3d = Polygon3D(coords)
                else:
                    poly3d = Polygon3D(surface.coords)
                x, y, z = poly3d.centroid
                X += x
                Y += y
                Z += z
            return X / dem, Y / dem, Z / dem

        # Get node positions in a dictionary
        pos = {name: avg(epbunch) for name, epbunch in
               self.nodes(data='epbunch')}

        # Get the maximum number of edges adjacent to a single node
        edge_max = max(1, max([self.degree(i) for i in self.nodes]))  # min = 1

        # Define color range proportional to number of edges adjacent to a
        # single node
        colors = {i: plt.cm.get_cmap(cmap)(self.degree(i) / edge_max) for i in
                  self.nodes}

        if annotate:
            # annotate can be bool or str.
            if isinstance(annotate, bool):
                # if True, default to 'Name' field
                annotate = 'Name'
            if isinstance(annotate, str):
                # create dict of the form {id: (x, y, z, label, zdir)}. zdir is
                # None by default.
                labels = {name: (*pos[name], data[annotate], None)
                          for name, data in self.nodes(data='epbunch')
                          }
            if isinstance(annotate, tuple):
                data, key = annotate
                if key:
                    labels = {name: (*pos[name], data[key], None)
                              for name, data in self.nodes(data=data)
                              }
                else:
                    labels = {name: (*pos[name], data, None)
                              for name, data in self.nodes(data=data)
                              }

        # 3D network plot
        with plt.style.context((plt_style)):
            if fig_height is None:
                fig_height = fig_width

            if ax:
                fig = plt.gcf()
            else:
                fig = plt.figure(figsize=(fig_width, fig_height), dpi=dpi)
                ax = Axes3D(fig)

            # Loop on the pos dictionary to extract the x,y,z coordinates of
            # each node
            for key, value in pos.items():
                xi = value[0]
                yi = value[1]
                zi = value[2]

                # Scatter plot
                ax.scatter(xi, yi, zi, color=colors[key],
                           s=20 + 20 * self.degree(
                               key), edgecolors='k', alpha=0.7)
                if annotate:
                    # Add node label
                    ax.text(*labels[key], fontsize=4)
            # Loop on the list of edges to get the x,y,z, coordinates of the
            # connected nodes
            # Those two points are the extrema of the line to be plotted
            for i, j in enumerate(self.edges()):
                x = np.array((pos[j[0]][0], pos[j[1]][0]))
                y = np.array((pos[j[0]][1], pos[j[1]][1]))
                z = np.array((pos[j[0]][2], pos[j[1]][2]))

                # Plot the connecting lines
                ax.plot(x, y, z, c='black', alpha=0.5)

        # Set the initial view
        ax.view_init(elev, azim)
        ax.set_proj_type(proj_type)

        # Hide the axes
        if axis_off:
            ax.set_axis_off()

        if filename is None:
            filename = 'unnamed'

        fig, ax = save_and_show(fig=fig, ax=ax, save=save, show=show,
                                close=close, filename=filename,
                                file_format=file_format, dpi=dpi,
                                axis_off=axis_off, extent=None)
        return fig, ax

    @property
    def core_graph(self):
        nodes = [i for i, data in self.nodes(data='core') if data]
        return self.subgraph(nodes).copy()

    def info(self, node=None):
        return print(networkx.info(G=self, n=node))


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
