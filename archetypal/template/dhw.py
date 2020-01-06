################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
from operator import add
from statistics import mean

import numpy as np
from archetypal import settings, log, timeit, reduce
from archetypal.template import Unique, UmiBase, UmiSchedule, UniqueName


class DomesticHotWaterSetting(UmiBase, metaclass=Unique):
    """Domestic Hot Water settigns

    .. image:: ../images/template/zoneinfo-dhw.png
    """

    def __init__(
        self,
        IsOn=True,
        WaterSchedule=None,
        FlowRatePerFloorArea=0.03,
        WaterSupplyTemperature=65,
        WaterTemperatureInlet=10,
        **kwargs
    ):
        """
        Args:
            IsOn (bool):
            WaterSchedule (UmiSchedule):
            FlowRatePerFloorArea (float):
            WaterSupplyTemperature (float):
            WaterTemperatureInlet (float):
            **kwargs:
        """
        super(DomesticHotWaterSetting, self).__init__(**kwargs)
        self.FlowRatePerFloorArea = FlowRatePerFloorArea
        self.IsOn = IsOn
        self.WaterSupplyTemperature = WaterSupplyTemperature
        self.WaterTemperatureInlet = WaterTemperatureInlet
        self.WaterSchedule = WaterSchedule

        self._belongs_to_zone = kwargs.get("zone", None)

    def __add__(self, other):
        """Overload + to implement self.combine

        Args:
            other (DomesticHotWaterSetting):
        """
        return self.combine(other)

    def __hash__(self):
        return hash((self.__class__.__name__, self.Name, self.DataSource))

    def __eq__(self, other):
        if not isinstance(other, DomesticHotWaterSetting):
            return False
        else:
            return all(
                [
                    self.IsOn == other.IsOn,
                    self.FlowRatePerFloorArea == other.FlowRatePerFloorArea,
                    self.WaterSupplyTemperature == other.WaterSupplyTemperature,
                    self.WaterTemperatureInlet == other.WaterTemperatureInlet,
                    self.WaterSchedule == other.WaterSchedule,
                ]
            )

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        dhws = cls(*args, **kwargs)
        wat_sch = kwargs.get("WaterSchedule", None)
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
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    @classmethod
    @timeit
    def from_zone(cls, zone):
        """Some WaterUse:Equipment objects can be assigned to a zone. :param
        zone: :type zone: Zone

        Args:
            zone (Zone):
        """
        # First, find the WaterUse:Equipement assigned to this zone
        dhw_objs = zone._epbunch.getreferingobjs(
            iddgroups=["Water Systems"], fields=["Zone_Name"]
        )
        if len(dhw_objs) > 1:
            # This zone has more than one WaterUse:Equipment object
            z_dhw_list = []
            for obj in dhw_objs:
                total_flow_rate = cls._do_flow_rate(dhw_objs, zone.area)
                water_schedule = cls._do_water_schedule(dhw_objs, zone)
                inlet_temp = cls._do_inlet_temp(dhw_objs, zone)
                supply_temp = cls._do_hot_temp(dhw_objs, zone)

                name = zone.Name + "_DHW"
                z_dhw = cls(
                    Name=name,
                    zone=zone,
                    FlowRatePerFloorArea=total_flow_rate,
                    IsOn=total_flow_rate > 0,
                    WaterSchedule=water_schedule,
                    WaterSupplyTemperature=supply_temp,
                    WaterTemperatureInlet=inlet_temp,
                    idf=zone.idf,
                    Category=zone.idf.building_name(use_idfname=True),
                )
                z_dhw_list.append(z_dhw)

            return reduce(add, z_dhw_list)

        elif len(dhw_objs) > 0:
            # Return dhw object for zone
            total_flow_rate = cls._do_flow_rate(dhw_objs, zone.area)
            water_schedule = cls._do_water_schedule(dhw_objs, zone)
            inlet_temp = cls._do_inlet_temp(dhw_objs, zone)
            supply_temp = cls._do_hot_temp(dhw_objs, zone)

            name = zone.Name + "_DHW"
            z_dhw = cls(
                Name=name,
                zone=zone,
                FlowRatePerFloorArea=total_flow_rate,
                IsOn=total_flow_rate > 0,
                WaterSchedule=water_schedule,
                WaterSupplyTemperature=supply_temp,
                WaterTemperatureInlet=inlet_temp,
                idf=zone.idf,
                Category=zone.idf.building_name(use_idfname=True),
            )
        else:
            # Assume water systems for whole building
            dhw_objs = zone.idf.idfobjects["WaterUse:Equipment".upper()]
            if dhw_objs:
                total_flow_rate = cls._do_flow_rate(dhw_objs, zone.idf.area_conditioned)
                water_schedule = cls._do_water_schedule(dhw_objs, zone)
                inlet_temp = cls._do_inlet_temp(dhw_objs, zone)
                supply_temp = cls._do_hot_temp(dhw_objs, zone)

                name = zone.Name + "_DHW"
                z_dhw = cls(
                    Name=name,
                    zone=zone,
                    FlowRatePerFloorArea=total_flow_rate,
                    IsOn=total_flow_rate > 0,
                    WaterSchedule=water_schedule,
                    WaterSupplyTemperature=supply_temp,
                    WaterTemperatureInlet=inlet_temp,
                    idf=zone.idf,
                    Category=zone.idf.building_name(use_idfname=True),
                )
            else:
                # defaults with 0 flow rate.
                total_flow_rate = 0
                water_schedule = UmiSchedule.constant_schedule(idf=zone._epbunch.theidf)
                supply_temp = 60
                inlet_temp = 10

                name = zone.Name + "_DHW"
                z_dhw = cls(
                    Name=name,
                    zone=zone,
                    FlowRatePerFloorArea=total_flow_rate,
                    IsOn=total_flow_rate > 0,
                    WaterSchedule=water_schedule,
                    WaterSupplyTemperature=supply_temp,
                    WaterTemperatureInlet=inlet_temp,
                    idf=zone.idf,
                    Category=zone.idf.building_name(use_idfname=True),
                )

        return z_dhw

    @classmethod
    @timeit
    def _do_hot_temp(cls, dhw_objs, zone):
        """
        Args:
            dhw_objs:
            zone:
        """
        hot_schds = []
        for obj in dhw_objs:
            # Reference to the schedule object specifying the target water
            # temperature [C]. If blank, the target temperature defaults to
            # the hot water supply temperature.
            schedule_name = (
                obj.Target_Temperature_Schedule_Name
                if obj.Target_Temperature_Schedule_Name != ""
                else obj.Hot_Water_Supply_Temperature_Schedule_Name
            )

            hot_schd = UmiSchedule(Name=schedule_name, idf=zone._epbunch.theidf)
            hot_schds.append(hot_schd)

        return np.array([sched.all_values.mean() for sched in hot_schds]).mean()

    @classmethod
    @timeit
    def _do_inlet_temp(cls, dhw_objs, zone):
        """Reference to the Schedule object specifying the cold water
        temperature [C] from the supply mains that provides the cold water to
        the tap and makes up for all water lost down the drain.

        Args:
            dhw_objs:
            zone:
        """
        WaterTemperatureInlet = []
        for obj in dhw_objs:
            if obj.Cold_Water_Supply_Temperature_Schedule_Name != "":
                # If a cold water supply schedule is provided, create the
                # schedule
                cold_schd_names = UmiSchedule(
                    Name=obj.Cold_Water_Supply_Temperature_Schedule_Name,
                    idf=zone._epbunch.theidf,
                )
                WaterTemperatureInlet.append(cold_schd_names.mean)
            else:
                # If blank, water temperatures are calculated by the
                # Site:WaterMainsTemperature object.
                water_mains_temps = zone._epbunch.theidf.idfobjects[
                    "Site:WaterMainsTemperature".upper()
                ]
                if water_mains_temps:
                    # If a "Site:WaterMainsTemperature" object exists,
                    # do water depending on calc method:
                    water_mains_temp = water_mains_temps[0]
                    if water_mains_temp.Calculation_Method.lower() == "schedule":
                        # From Schedule method
                        mains_scd = UmiSchedule(
                            Name=water_mains_temp.Schedule_Name,
                            idf=zone._epbunch.theidf,
                        )
                        WaterTemperatureInlet.append(mains_scd.mean())
                    elif water_mains_temp.Calculation_Method.lower() == "correlation":
                        # From Correlation method
                        mean_outair_temp = (
                            water_mains_temp.Annual_Average_Outdoor_Air_Temperature
                        )
                        max_dif = (
                            water_mains_temp.Maximum_Difference_In_Monthly_Average_Outdoor_Air_Temperatures
                        )

                        WaterTemperatureInlet.append(
                            water_main_correlation(mean_outair_temp, max_dif).mean()
                        )
                else:
                    # Else, there is no Site:WaterMainsTemperature object in
                    # the input file, a default constant value of 10 C is
                    # assumed.
                    WaterTemperatureInlet.append(float(10))
        return mean(WaterTemperatureInlet)

    @classmethod
    @timeit
    def _do_water_schedule(cls, dhw_objs, zone):
        """Returns the WaterSchedule for a list of WaterUse:Equipment objects.
        If more than one objects are passed, a combined schedule is returned

        Args:
            dhw_objs:
            zone:
        """
        water_schds = collections.defaultdict(dict)
        for obj in dhw_objs:
            water_schd_name = UmiSchedule(
                Name=obj.Flow_Rate_Fraction_Schedule_Name, idf=zone._epbunch.theidf
            )
            water_schds[water_schd_name.Name]["schedule"] = water_schd_name
            water_schds[water_schd_name.Name]["quantity"] = obj.Peak_Flow_Rate
        return reduce(
            UmiSchedule.combine,
            [v["schedule"] for k, v in water_schds.items()],
            weights=None,
            quantity={k: v["quantity"] for k, v in water_schds.items()},
        )

    @classmethod
    @timeit
    def _do_flow_rate(cls, dhw_objs, area):
        """Calculate total flow rate from list of WaterUse:Equipment objects.
        The zone's area_conditioned property is used to normalize the flow rate.

        Args:
            dhw_objs (Idf_MSequence):
            zone (Zone):
        """
        total_flow_rate = 0
        for obj in dhw_objs:
            total_flow_rate += obj.Peak_Flow_Rate  # m3/s
        total_flow_rate /= area  # m3/s/m2
        total_flow_rate *= 3600.0  # m3/h/m2
        return total_flow_rate

    def combine(self, other, weights=None):
        """Combine two DomesticHotWaterSetting objects together.

        Args:
            other (DomesticHotWaterSetting):
            weights (list-like, optional): A list-like object of len 2. If None,
                the volume of the zones for which self and other belongs is
                used.

        Returns:
            (DomesticHotWaterSetting): a new combined object
        """
        if self is None:
            return other
        if other is None:
            return self
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

        new_obj = DomesticHotWaterSetting(
            **meta,
            IsOn=any((self.IsOn, other.IsOn)),
            WaterSchedule=self.WaterSchedule.combine(
                other.WaterSchedule,
                weights,
                [self.FlowRatePerFloorArea, other.FlowRatePerFloorArea],
            ),
            FlowRatePerFloorArea=self._float_mean(
                other, "FlowRatePerFloorArea", weights
            ),
            WaterSupplyTemperature=self._float_mean(
                other, "WaterSupplyTemperature", weights
            ),
            WaterTemperatureInlet=self._float_mean(
                other, "WaterTemperatureInlet", weights
            )
        )
        new_obj._predecessors.extend(self.predecessors + other.predecessors)
        return new_obj


def water_main_correlation(t_out_avg, max_diff):
    """Based on the coorelation by correlation was developed by Craig
    Christensen and Jay Burch.

    Returns a 365 days temperature profile.

    Info:
        https://bigladdersoftware.com/epx/docs/8-9/engineering-reference
        /water-systems.html#water-mains-temperatures

    Args:
        t_out_avg (float): average annual outdoor air temperature (°C).
        max_diff (float): maximum difference in monthly average outdoor air
            temperatures (°C).

    Returns:
        (pd.Series): water mains temperature profile.
    """
    import numpy as np
    import pandas as pd

    Q_ = settings.unit_registry.Quantity
    t_out_avg_F = Q_(t_out_avg, "degC").to("degF")
    max_diff_F = Q_(max_diff, "delta_degC").to("delta_degF")
    ratio = 0.4 + 0.01 * (t_out_avg_F.m - 44)
    lag = 35 - 1.0 * (t_out_avg_F.m - 44)
    days = np.arange(1, 365)
    function = lambda t_out_avg, day, max_diff: (t_out_avg + 6) + ratio * (
        max_diff / 2
    ) * np.sin(np.deg2rad(0.986 * (day - 15 - lag) - 90))
    mains = [Q_(function(t_out_avg_F.m, day, max_diff_F.m), "degF") for day in days]
    series = pd.Series([temp.to("degC").m for temp in mains])
    return series
