################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import logging as lg

import numpy as np
import pandas as pd
from deprecation import deprecated
from sigfig import round

import archetypal
from archetypal import log, settings, timeit, top, weighted_mean
from archetypal.template import UmiBase, UmiSchedule, UniqueName


def resolve_temp(temp, idf):
    """Resolve the temperature. If a float is passed, simply return it. If a str
    is passed, get the schedule and return the mean value.

    Args:
        temp (float or str):
        idf (IDF): the idf object
    """
    if isinstance(temp, float):
        return temp
    elif isinstance(temp, str):
        sched = UmiSchedule(Name=temp, idf=idf)
        return sched.all_values.mean()


class VentilationSetting(UmiBase):
    """Zone Ventilation Settings

    .. image:: ../images/template/zoneinfo-ventilation.png
    """

    def __init__(
        self,
        NatVentSchedule=None,
        ScheduledVentilationSchedule=None,
        Afn=False,
        Infiltration=0.1,
        IsBuoyancyOn=True,
        IsInfiltrationOn=True,
        IsNatVentOn=False,
        IsScheduledVentilationOn=False,
        IsWindOn=False,
        NatVentMaxOutdoorAirTemp=30,
        NatVentMaxRelHumidity=90,
        NatVentMinOutdoorAirTemp=0,
        NatVentZoneTempSetpoint=18,
        ScheduledVentilationAch=0.6,
        ScheduledVentilationSetpoint=18,
        **kwargs
    ):
        """Initialize a new VentilationSetting (for zone) object

        Args:
            NatVentSchedule (UmiSchedule): The name of the schedule
                (Day | Week | Year) which ultimately modifies the Opening Area
                value (see previous field). In its current implementation, any
                value greater than 0 will consider, value above The schedule
                values must be any positive number between 0 and 1 as a
                fraction.
            ScheduledVentilationSchedule (UmiSchedule): The name of
                the schedule (Schedules Tab) that modifies the maximum design
                volume flow rate. This fraction is between 0.0 and 1.0.
            Afn (bool):
            Infiltration (float): Infiltration rate in ACH
            IsBuoyancyOn (bool): If True, simulation takes into account the
                stack effect in the infiltration calculation
            IsInfiltrationOn (bool): If yes, there is heat transfer between the
                building and the outside caused by infiltration
            IsNatVentOn (bool): If True, Natural ventilation (air
                movement/exchange as a result of openings in the building façade
                not consuming any fan energy).
            IsScheduledVentilationOn (bool): If True, Ventilation (flow of air
                from the outdoor environment directly into a thermal zone) is ON
            IsWindOn (bool): If True, simulation takes into account the wind
                effect in the infiltration calculation
            NatVentMaxOutdoorAirTemp (float): The outdoor temperature (in
                Celsius) above which ventilation is shut off. The minimum value
                for this field is -100.0°C and the maximum value is 100.0°C. The
                default value is 100.0°C if the field is left blank. This upper
                temperature limit is intended to avoid overheating a space,
                which could result in a cooling load.
            NatVentMaxRelHumidity (float): Defines the dehumidifying relative
                humidity setpoint, expressed as a percentage (0-100), for each
                timestep of the simulation.
            NatVentMinOutdoorAirTemp (float): The outdoor temperature (in
                Celsius) below which ventilation is shut off. The minimum value
                for this field is -100.0°C and the maximum value is 100.0°C. The
                default value is -100.0°C if the field is left blank. This lower
                temperature limit is intended to avoid overcooling a space,
                which could result in a heating load.
            NatVentZoneTempSetpoint (float):
            ScheduledVentilationAch (float): This factor, along with the Zone
                Volume, will be used to determine the Design Flow Rate.
            ScheduledVentilationSetpoint (float): The indoor temperature (in
                Celsius) below which ventilation is shutoff. The minimum value
                for this field is -100.0°C and the maximum value is 100.0°C. The
                default value is -100.0°C if the field is left blank. This lower
                temperature limit is intended to avoid overcooling a space and
                thus result in a heating load. For example, if the user
                specifies a minimum temperature of 20°C, ventilation is assumed
                to be available if the zone air temperature is above 20°C. If
                the zone air temperature drops below 20°C, then ventilation is
                automatically turned off.
            **kwargs:
        """
        super(VentilationSetting, self).__init__(**kwargs)
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

        self._belongs_to_zone = kwargs.get("zone", None)

    @property
    def Infiltration(self):
        return float(self._Infiltration)

    @Infiltration.setter
    def Infiltration(self, value):
        self._Infiltration = value

    @property
    def NatVentMaxOutdoorAirTemp(self):
        return float(self._NatVentMaxOutdoorAirTemp)

    @NatVentMaxOutdoorAirTemp.setter
    def NatVentMaxOutdoorAirTemp(self, value):
        self._NatVentMaxOutdoorAirTemp = value

    @property
    def NatVentMaxRelHumidity(self):
        return float(self._NatVentMaxRelHumidity)

    @NatVentMaxRelHumidity.setter
    def NatVentMaxRelHumidity(self, value):
        self._NatVentMaxRelHumidity = value

    @property
    def NatVentMinOutdoorAirTemp(self):
        return float(self._NatVentMinOutdoorAirTemp)

    @NatVentMinOutdoorAirTemp.setter
    def NatVentMinOutdoorAirTemp(self, value):
        self._NatVentMinOutdoorAirTemp = value

    @property
    def NatVentZoneTempSetpoint(self):
        return float(self._NatVentZoneTempSetpoint)

    @NatVentZoneTempSetpoint.setter
    def NatVentZoneTempSetpoint(self, value):
        self._NatVentZoneTempSetpoint = value

    @property
    def ScheduledVentilationAch(self):
        return float(self._ScheduledVentilationAch)

    @ScheduledVentilationAch.setter
    def ScheduledVentilationAch(self, value):
        self._ScheduledVentilationAch = value

    @property
    def ScheduledVentilationSetpoint(self):
        return float(self._ScheduledVentilationSetpoint)

    @ScheduledVentilationSetpoint.setter
    def ScheduledVentilationSetpoint(self, value):
        self._ScheduledVentilationSetpoint = value

    def __add__(self, other):
        return self.combine(other)

    def __hash__(self):
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __eq__(self, other):
        if not isinstance(other, VentilationSetting):
            return NotImplemented
        else:
            return all(
                [
                    self.NatVentSchedule == other.NatVentSchedule,
                    self.ScheduledVentilationSchedule
                    == self.ScheduledVentilationSchedule,
                    self.Afn == other.Afn,
                    self.Infiltration == other.Infiltration,
                    self.IsBuoyancyOn == other.IsBuoyancyOn,
                    self.IsInfiltrationOn == other.IsInfiltrationOn,
                    self.IsNatVentOn == other.IsNatVentOn,
                    self.IsScheduledVentilationOn == other.IsScheduledVentilationOn,
                    self.IsWindOn == other.IsWindOn,
                    self.NatVentMaxOutdoorAirTemp == other.NatVentMaxOutdoorAirTemp,
                    self.NatVentMaxRelHumidity == other.NatVentMaxRelHumidity,
                    self.NatVentMinOutdoorAirTemp == other.NatVentMinOutdoorAirTemp,
                    self.NatVentZoneTempSetpoint == other.NatVentZoneTempSetpoint,
                    self.ScheduledVentilationAch == other.ScheduledVentilationAch,
                    self.ScheduledVentilationSetpoint
                    == other.ScheduledVentilationSetpoint,
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
        """
        Args:
            *args:
            **kwargs:
        """
        vs = cls(*args, **kwargs)
        vent_sch = kwargs.get("ScheduledVentilationSchedule", None)
        vs.ScheduledVentilationSchedule = vs.get_ref(vent_sch)
        nat_sch = kwargs.get("NatVentSchedule", None)
        vs.NatVentSchedule = vs.get_ref(nat_sch)
        return vs

    def to_json(self):
        """Convert class properties to dict"""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Afn"] = self.Afn
        data_dict["IsBuoyancyOn"] = self.IsBuoyancyOn
        data_dict["Infiltration"] = round(self.Infiltration, 3)
        data_dict["IsInfiltrationOn"] = self.IsInfiltrationOn
        data_dict["IsNatVentOn"] = self.IsNatVentOn
        data_dict["IsScheduledVentilationOn"] = self.IsScheduledVentilationOn
        data_dict["NatVentMaxRelHumidity"] = round(self.NatVentMaxRelHumidity, 3)
        data_dict["NatVentMaxOutdoorAirTemp"] = round(self.NatVentMaxOutdoorAirTemp, 3)
        data_dict["NatVentMinOutdoorAirTemp"] = round(self.NatVentMinOutdoorAirTemp, 3)
        data_dict["NatVentSchedule"] = self.NatVentSchedule.to_dict()
        data_dict["NatVentZoneTempSetpoint"] = round(self.NatVentZoneTempSetpoint, 3)
        data_dict["ScheduledVentilationAch"] = round(self.ScheduledVentilationAch, 3)
        data_dict[
            "ScheduledVentilationSchedule"
        ] = self.ScheduledVentilationSchedule.to_dict()
        data_dict["ScheduledVentilationSetpoint"] = round(
            self.ScheduledVentilationSetpoint, 3
        )
        data_dict["IsWindOn"] = self.IsWindOn
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    @classmethod
    @timeit
    def from_zone(cls, zone, **kwargs):
        """

        Args:
            zone (template.zone.Zone): zone to gets information from
        """
        # If Zone is not part of Conditioned Area, it should not have a
        # VentilationSetting object.
        if not zone.is_part_of_total_floor_area:
            return None
        name = zone.Name + "_VentilationSetting"

        df = {"a": zone.idf.sql()}
        ni_df = nominal_infiltration(df)
        sched_df = nominal_mech_ventilation(df)
        nat_df = nominal_nat_ventilation(df)
        index = ("a", zone.Name.upper())

        # Do infiltration
        Infiltration, IsInfiltrationOn = do_infiltration(index, ni_df, zone)

        # Do natural ventilation
        (
            IsNatVentOn,
            IsWindOn,
            IsBuoyancyOn,
            NatVentMaxOutdoorAirTemp,
            NatVentMaxRelHumidity,
            NatVentMinOutdoorAirTemp,
            NatVentSchedule,
            NatVentZoneTempSetpoint,
        ) = do_natural_ventilation(index, nat_df, zone)

        # Do scheduled ventilation
        (
            ScheduledVentilationSchedule,
            IsScheduledVentilationOn,
            ScheduledVentilationAch,
            ScheduledVentilationSetpoint,
        ) = do_scheduled_ventilation(index, sched_df, zone)

        z_vent = cls(
            Name=name,
            zone=zone,
            Infiltration=Infiltration,
            IsInfiltrationOn=IsInfiltrationOn,
            IsWindOn=IsWindOn,
            IsBuoyancyOn=IsBuoyancyOn,
            IsNatVentOn=IsNatVentOn,
            NatVentSchedule=NatVentSchedule,
            NatVentMaxRelHumidity=NatVentMaxRelHumidity,
            NatVentMaxOutdoorAirTemp=NatVentMaxOutdoorAirTemp,
            NatVentMinOutdoorAirTemp=NatVentMinOutdoorAirTemp,
            NatVentZoneTempSetpoint=NatVentZoneTempSetpoint,
            ScheduledVentilationSchedule=ScheduledVentilationSchedule,
            IsScheduledVentilationOn=IsScheduledVentilationOn,
            ScheduledVentilationAch=ScheduledVentilationAch,
            ScheduledVentilationSetpoint=ScheduledVentilationSetpoint,
            idf=zone.idf,
            Category=zone.idf.name,
            **kwargs
        )
        return z_vent

    def combine(self, other, weights=None):
        """Combine two VentilationSetting objects together.

        Args:
            other (VentilationSetting):
            weights (list-like, optional): A list-like object of len 2. If None,
                the volume of the zones for which self and other belongs is
                used.

        Returns:
            (VentilationSetting): the combined VentilationSetting object.
        """
        # Check if other is None. Simply return self
        if not other:
            return self

        if not self:
            return other

        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = "Cannot combine %s with %s" % (
                self.__class__.__name__,
                other.__class__.__name__,
            )
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        meta = self._get_predecessors_meta(other)

        if not weights:
            zone_weight = settings.zone_weight
            weights = [
                getattr(self._belongs_to_zone, str(zone_weight)),
                getattr(other._belongs_to_zone, str(zone_weight)),
            ]
            log(
                'using zone {} "{}" as weighting factor in "{}" '
                "combine.".format(
                    zone_weight,
                    " & ".join(list(map(str, map(int, weights)))),
                    self.__class__.__name__,
                )
            )

        a = UmiSchedule.combine(self.NatVentSchedule, other.NatVentSchedule, weights)
        b = UmiSchedule.combine(
            self.ScheduledVentilationSchedule,
            other.ScheduledVentilationSchedule,
            weights,
        )
        c = any((self.Afn, other.Afn))
        d = self._float_mean(other, "Infiltration", weights)
        e = any((self.IsBuoyancyOn, other.IsBuoyancyOn))
        f = any((self.IsInfiltrationOn, other.IsInfiltrationOn))
        g = any((self.IsNatVentOn, other.IsNatVentOn))
        h = any((self.IsScheduledVentilationOn, other.IsScheduledVentilationOn))
        i = any((self.IsWindOn, other.IsWindOn))
        j = self._float_mean(other, "NatVentMaxOutdoorAirTemp", weights)
        k = self._float_mean(other, "NatVentMaxRelHumidity", weights)
        l = self._float_mean(other, "NatVentMinOutdoorAirTemp", weights)
        m = self._float_mean(other, "NatVentZoneTempSetpoint", weights)
        n = self._float_mean(other, "ScheduledVentilationAch", weights)
        o = self._float_mean(other, "ScheduledVentilationSetpoint", weights)

        new_attr = dict(
            NatVentSchedule=a,
            ScheduledVentilationSchedule=b,
            Afn=c,
            Infiltration=d,
            IsBuoyancyOn=e,
            IsInfiltrationOn=f,
            IsNatVentOn=g,
            IsScheduledVentilationOn=h,
            IsWindOn=i,
            NatVentMaxOutdoorAirTemp=j,
            NatVentMaxRelHumidity=k,
            NatVentMinOutdoorAirTemp=l,
            NatVentZoneTempSetpoint=m,
            ScheduledVentilationAch=n,
            ScheduledVentilationSetpoint=o,
        )

        # create a new object with the previous attributes
        new_obj = self.__class__(
            **meta, **new_attr, idf=self.idf, allow_duplicates=self._allow_duplicates
        )
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def validate(self):
        """Validate object and fill in missing values."""
        if not self.NatVentSchedule:
            self.NatVentSchedule = UmiSchedule.constant_schedule(
                hourly_value=0, Name="AlwaysOff", allow_duplicates=True, idf=self.idf
            )
        if not self.ScheduledVentilationSchedule:
            self.ScheduledVentilationSchedule = UmiSchedule.constant_schedule(
                hourly_value=0, Name="AlwaysOff", allow_duplicates=True, idf=self.idf
            )

        return self

    def mapping(self):
        self.validate()

        return dict(
            Afn=self.Afn,
            IsBuoyancyOn=self.IsBuoyancyOn,
            Infiltration=self.Infiltration,
            IsInfiltrationOn=self.IsInfiltrationOn,
            IsNatVentOn=self.IsNatVentOn,
            IsScheduledVentilationOn=self.IsScheduledVentilationOn,
            NatVentMaxRelHumidity=self.NatVentMaxRelHumidity,
            NatVentMaxOutdoorAirTemp=self.NatVentMaxOutdoorAirTemp,
            NatVentMinOutdoorAirTemp=self.NatVentMinOutdoorAirTemp,
            NatVentSchedule=self.NatVentSchedule,
            NatVentZoneTempSetpoint=self.NatVentZoneTempSetpoint,
            ScheduledVentilationAch=self.ScheduledVentilationAch,
            ScheduledVentilationSchedule=self.ScheduledVentilationSchedule,
            ScheduledVentilationSetpoint=self.ScheduledVentilationSetpoint,
            IsWindOn=self.IsWindOn,
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
                    for value in VentilationSetting.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )


def do_infiltration(index, inf_df, zone):
    """Gets infiltration information of the zone

    Args:
        index (tuple): Zone name
        inf_df (dataframe): Dataframe with infiltration information for each
            zone
        zone (template.zone.Zone): zone to gets information from
    """
    if not inf_df.empty:
        try:
            Infiltration = inf_df.loc[index, "ACH - Air Changes per Hour"]
            IsInfiltrationOn = any(inf_df.loc[index, "Name"])
        except:
            Infiltration = 0
            IsInfiltrationOn = False
    else:
        Infiltration = 0
        IsInfiltrationOn = False
    return Infiltration, IsInfiltrationOn


def do_natural_ventilation(index, nat_df, zone):
    """Gets natural ventilation information of the zone

    Args:
        index (tuple): Zone name
        nat_df:
        zone (template.zone.Zone): zone to gets information from
    """
    if not nat_df.empty:
        try:
            IsNatVentOn = any(nat_df.loc[index, "Name"])
            schedule_name_ = nat_df.loc[index, "Schedule Name"]
            quantity = nat_df.loc[index, "Volume Flow Rate/Floor Area {m3/s/m2}"]
            if schedule_name_.upper() in zone.idf.schedules_dict:
                NatVentSchedule = UmiSchedule(
                    Name=schedule_name_, idf=zone.idf, quantity=quantity
                )
            else:
                raise KeyError
        except KeyError:
            # todo: For some reason, a ZoneVentilation:WindandStackOpenArea
            #  'Opening Area Fraction Schedule Name' is read as Constant-0.0
            #  in the nat_df. For the mean time, a zone containing such an
            #  object will be turned on with an AlwaysOn schedule.
            IsNatVentOn = True
            NatVentSchedule = UmiSchedule.constant_schedule(
                idf=zone.idf, allow_duplicates=True
            )
        except Exception:
            IsNatVentOn = False
            NatVentSchedule = UmiSchedule.constant_schedule(
                idf=zone.idf, allow_duplicates=True
            )
        finally:
            try:
                NatVentMaxRelHumidity = 90  # todo: not sure if it is being used
                NatVentMaxOutdoorAirTemp = resolve_temp(
                    nat_df.loc[index, "Maximum Outdoor Temperature{C}/Schedule"],
                    zone.idf,
                )
                NatVentMinOutdoorAirTemp = resolve_temp(
                    nat_df.loc[index, "Minimum Outdoor Temperature{C}/Schedule"],
                    zone.idf,
                )
                NatVentZoneTempSetpoint = resolve_temp(
                    nat_df.loc[index, "Minimum Indoor Temperature{C}/Schedule"],
                    zone.idf,
                )
            except KeyError:
                # this zone is not in the nat_df. Revert to defaults.
                NatVentMaxRelHumidity = 90
                NatVentMaxOutdoorAirTemp = 30
                NatVentMinOutdoorAirTemp = 0
                NatVentZoneTempSetpoint = 18

    else:
        IsNatVentOn = False
        NatVentSchedule = UmiSchedule.constant_schedule(
            idf=zone.idf, allow_duplicates=True
        )
        NatVentMaxRelHumidity = 90
        NatVentMaxOutdoorAirTemp = 30
        NatVentMinOutdoorAirTemp = 0
        NatVentZoneTempSetpoint = 18

    # Is Wind ON
    if not zone.idf.idfobjects["ZoneVentilation:WindandStackOpenArea".upper()].list1:
        IsWindOn = False
        IsBuoyancyOn = False
    else:
        IsWindOn = True
        IsBuoyancyOn = True

    return (
        IsNatVentOn,
        IsWindOn,
        IsBuoyancyOn,
        NatVentMaxOutdoorAirTemp,
        NatVentMaxRelHumidity,
        NatVentMinOutdoorAirTemp,
        NatVentSchedule,
        NatVentZoneTempSetpoint,
    )


def do_scheduled_ventilation(index, scd_df, zone):
    """Gets schedule ventilation information of the zone

    Args:
        index (tuple): Zone name
        scd_df:
        zone (template.zone.Zone): zone to gets information from
    """
    if not scd_df.empty:
        try:
            IsScheduledVentilationOn = any(scd_df.loc[index, "Name"])
            schedule_name_ = scd_df.loc[index, "Schedule Name"]
            ScheduledVentilationSchedule = UmiSchedule(
                Name=schedule_name_, idf=zone.idf
            )
            ScheduledVentilationAch = scd_df.loc[index, "ACH - Air Changes per Hour"]
            ScheduledVentilationSetpoint = resolve_temp(
                scd_df.loc[index, "Minimum Indoor Temperature{C}/Schedule"],
                zone.idf,
            )
        except:
            ScheduledVentilationSchedule = UmiSchedule.constant_schedule(
                hourly_value=0, Name="AlwaysOff", idf=zone.idf, allow_duplicates=True
            )
            IsScheduledVentilationOn = False
            ScheduledVentilationAch = 0
            ScheduledVentilationSetpoint = 18
    else:
        ScheduledVentilationSchedule = UmiSchedule.constant_schedule(
            hourly_value=0, Name="AlwaysOff", idf=zone.idf, allow_duplicates=True
        )
        IsScheduledVentilationOn = False
        ScheduledVentilationAch = 0
        ScheduledVentilationSetpoint = 18
    return (
        ScheduledVentilationSchedule,
        IsScheduledVentilationOn,
        ScheduledVentilationAch,
        ScheduledVentilationSetpoint,
    )


def nominal_nat_ventilation(df):
    _nom_vent = nominal_ventilation(df)
    if _nom_vent.empty:
        return _nom_vent
    nom_natvent = (
        _nom_vent.reset_index()
        .set_index(["Archetype", "Zone Name"])
        .loc[
            lambda e: e["Fan Type {Exhaust;Intake;Natural}"].str.contains("Natural"), :
        ]
        if not _nom_vent.empty
        else None
    )
    return nom_natvent


def nominal_mech_ventilation(df):
    _nom_vent = nominal_ventilation(df)
    if _nom_vent.empty:
        return _nom_vent
    nom_vent = (
        _nom_vent.reset_index()
        .set_index(["Archetype", "Zone Name"])
        .loc[
            lambda e: ~e["Fan Type {Exhaust;Intake;Natural}"].str.contains("Natural"), :
        ]
        if not _nom_vent.empty
        else None
    )
    return nom_vent


def nominal_infiltration(df):
    """Nominal Infiltration

    Args:
        df:

    Returns:
        df

    References:
        * `Nominal Infiltration Table \
        <https://bigladdersoftware.com/epx/docs/8-9/output-details-and \
        -examples/eplusout-sql.html#nominalinfiltration-table>`_

    """
    df = get_from_tabulardata(df)
    report_name = "Initialization Summary"
    table_name = "ZoneInfiltration Airflow Stats Nominal"
    tbstr = df[
        (df.ReportName == report_name) & (df.TableName == table_name)
    ].reset_index()
    if tbstr.empty:
        log(
            "Table {} does not exist. "
            "Returning an empty DataFrame".format(table_name),
            lg.WARNING,
        )
        return pd.DataFrame([])

    tbpiv = tbstr.pivot_table(
        index=["Archetype", "RowName"],
        columns="ColumnName",
        values="Value",
        aggfunc=lambda x: " ".join(x),
    )
    tbpiv.replace({"N/A": np.nan}, inplace=True)
    return (
        tbpiv.reset_index()
        .groupby(["Archetype", "Zone Name"])
        .agg(lambda x: pd.to_numeric(x, errors="ignore").sum())
    )


def nominal_ventilation(df):
    """Nominal Ventilation

    Args:
        df:

    Returns:
        df

    References:
        * `Nominal Ventilation Table \
        <https://bigladdersoftware.com/epx/docs/8-9/output-details-and \
        -examples/eplusout-sql.html#nominalventilation-table>`_

    """
    df = get_from_tabulardata(df)
    report_name = "Initialization Summary"
    table_name = "ZoneVentilation Airflow Stats Nominal"
    tbstr = df[
        (df.ReportName == report_name) & (df.TableName == table_name)
    ].reset_index()
    if tbstr.empty:
        log(
            "Table {} does not exist. "
            "Returning an empty DataFrame".format(table_name),
            lg.WARNING,
        )
        return pd.DataFrame([])
    tbpiv = tbstr.pivot_table(
        index=["Archetype", "RowName"],
        columns="ColumnName",
        values="Value",
        aggfunc=lambda x: " ".join(x),
    )

    tbpiv = tbpiv.replace({"N/A": np.nan}).apply(
        lambda x: pd.to_numeric(x, errors="ignore")
    )
    tbpiv = (
        tbpiv.reset_index()
        .groupby(["Archetype", "Zone Name", "Fan Type {Exhaust;Intake;Natural}"])
        .apply(nominal_ventilation_aggregation)
    )
    return tbpiv
    # .reset_index().groupby(['Archetype', 'Zone Name']).agg(
    # lambda x: pd.to_numeric(x, errors='ignore').sum())


def nominal_ventilation_aggregation(x):
    """Aggregates the ventilations whithin a single zone_loads name (implies
    that
    .groupby(['Archetype', 'Zone Name']) is
    performed before calling this function).

    Args:
        x:

    Returns:
        A DataFrame with at least one entry per ('Archetype', 'Zone Name'),
        aggregated accordingly.
    """
    how_dict = {
        "Name": top(x["Name"], x, "Zone Floor Area {m2}"),
        "Schedule Name": top(x["Schedule Name"], x, "Zone Floor Area {m2}"),
        "Zone Floor Area {m2}": top(
            x["Zone Floor Area {m2}"], x, "Zone Floor Area {m2}"
        ),
        "# Zone Occupants": top(x["# Zone Occupants"], x, "Zone Floor Area {m2}"),
        "Design Volume Flow Rate {m3/s}": weighted_mean(
            x["Design Volume Flow Rate {m3/s}"], x, "Zone Floor Area {m2}"
        ),
        "Volume Flow Rate/Floor Area {m3/s/m2}": weighted_mean(
            x.filter(like="Volume Flow Rate/Floor Area").squeeze(axis=1),
            x,
            "Zone Floor Area {m2}",
        ),
        "Volume Flow Rate/person Area {m3/s/person}": weighted_mean(
            x.filter(like="Volume Flow Rate/person Area").squeeze(axis=1),
            x,
            "Zone Floor " "Area {m2}",
        ),
        "ACH - Air Changes per Hour": weighted_mean(
            x["ACH - Air Changes per Hour"], x, "Zone Floor Area {m2}"
        ),
        "Fan Pressure Rise {Pa}": weighted_mean(
            x["Fan Pressure Rise {Pa}"], x, "Zone Floor Area {m2}"
        ),
        "Fan Efficiency {}": weighted_mean(
            x["Fan Efficiency {}"], x, "Zone Floor Area {m2}"
        ),
        "Equation A - Constant Term Coefficient {}": top(
            x["Equation A - Constant Term Coefficient {}"], x, "Zone Floor Area {m2}"
        ),
        "Equation B - Temperature Term Coefficient {1/C}": top(
            x["Equation B - Temperature Term Coefficient {1/C}"],
            x,
            "Zone Floor Area {m2}",
        ),
        "Equation C - Velocity Term Coefficient {s/m}": top(
            x["Equation C - Velocity Term Coefficient {s/m}"], x, "Zone Floor Area {m2}"
        ),
        "Equation D - Velocity Squared Term Coefficient {s2/m2}": top(
            x["Equation D - Velocity Squared Term Coefficient {s2/m2}"],
            x,
            "Zone Floor Area {m2}",
        ),
        "Minimum Indoor Temperature{C}/Schedule": top(
            x["Minimum Indoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Maximum Indoor Temperature{C}/Schedule": top(
            x["Maximum Indoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Delta Temperature{C}/Schedule": top(
            x["Delta Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Minimum Outdoor Temperature{C}/Schedule": top(
            x["Minimum Outdoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Maximum Outdoor Temperature{C}/Schedule": top(
            x["Maximum Outdoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Maximum WindSpeed{m/s}": top(
            x["Maximum WindSpeed{m/s}"], x, "Zone Floor Area {m2}"
        ),
    }
    try:
        df = pd.DataFrame(how_dict, index=range(0, 1))  # range should always be
        # one since we are trying to merge zones
    except Exception as e:
        log("{}".format(e))
    else:
        return df


def get_from_tabulardata(results):
    """Returns a DataFrame from the 'TabularDataWithStrings' table. A
    multiindex is returned with names ['Archetype', 'Index']

    Args:
        results:

    Returns:

    """
    tab_data_wstring = pd.concat(
        [value["TabularDataWithStrings"] for value in results.values()],
        keys=results.keys(),
        names=["Archetype"],
    )
    tab_data_wstring.index.names = ["Archetype", "Index"]  #
    # strip whitespaces
    tab_data_wstring.Value = tab_data_wstring.Value.str.strip()
    tab_data_wstring.RowName = tab_data_wstring.RowName.str.strip()
    return tab_data_wstring
