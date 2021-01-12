################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
from statistics import mean

import numpy as np
from deprecation import deprecated
from sigfig import round

import archetypal
from archetypal import log, reduce, settings, timeit
from archetypal.template import UmiBase, UmiSchedule, UniqueName


class DomesticHotWaterSetting(UmiBase):
    """Domestic Hot Water settings

    .. image:: ../images/template/zoneinfo-dhw.png
    """

    def __init__(
        self,
        IsOn=True,
        WaterSchedule=None,
        FlowRatePerFloorArea=0.03,
        WaterSupplyTemperature=65,
        WaterTemperatureInlet=10,
        **kwargs,
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
        self._belongs_to_zone = kwargs.get("Zone", None)

    @property
    def FlowRatePerFloorArea(self):
        return float(self._FlowRatePerFloorArea)

    @FlowRatePerFloorArea.setter
    def FlowRatePerFloorArea(self, value):
        self._FlowRatePerFloorArea = value

    @property
    def WaterSupplyTemperature(self):
        return float(self._WaterSupplyTemperature)

    @WaterSupplyTemperature.setter
    def WaterSupplyTemperature(self, value):
        self._WaterSupplyTemperature = value

    @property
    def WaterTemperatureInlet(self):
        return float(self._WaterTemperatureInlet)

    @WaterTemperatureInlet.setter
    def WaterTemperatureInlet(self, value):
        self._WaterTemperatureInlet = value

    @property
    def Zone(self):
        return self._belongs_to_zone

    @Zone.setter
    def Zone(self, value):
        self._belongs_to_zone = value

    def __add__(self, other):
        """Overload + to implement self.combine

        Args:
            other (DomesticHotWaterSetting):
        """
        return self.combine(other)

    def __hash__(self):
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __eq__(self, other):
        if not isinstance(other, DomesticHotWaterSetting):
            return NotImplemented
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

    def __str__(self):
        return (
            f"{str(self.id)}: {str(self.Name)} "
            f"PeakFlow {self.FlowRatePerFloorArea:.5f} m3/hr/m2"
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
        dhws = cls(*args, **kwargs)
        wat_sch = kwargs.get("WaterSchedule", None)
        dhws.WaterSchedule = dhws.get_ref(wat_sch)
        return dhws

    def to_json(self):
        """Convert class properties to dict"""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["FlowRatePerFloorArea"] = round(self.FlowRatePerFloorArea, sigfigs=4)
        data_dict["IsOn"] = self.IsOn
        data_dict["WaterSchedule"] = self.WaterSchedule.to_dict()
        data_dict["WaterSupplyTemperature"] = round(
            self.WaterSupplyTemperature, sigfigs=4
        )
        data_dict["WaterTemperatureInlet"] = round(
            self.WaterTemperatureInlet, sigfigs=4
        )
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    @classmethod
    @timeit
    def from_zone(cls, zone, **kwargs):
        """Some WaterUse:Equipment objects can be assigned to a zone. :param
        zone: :type zone: Zone

        Args:
            zone (Zone):
        """
        # If Zone is not part of Conditioned Area, it should not have a DHW object.
        if not zone.is_part_of_conditioned_floor_area:
            return None

        # First, find the WaterUse:Equipment assigned to this zone
        dhw_objs = zone._epbunch.getreferingobjs(
            iddgroups=["Water Systems"], fields=["Zone_Name"]
        )
        if dhw_objs:
            # This zone has more than one WaterUse:Equipment object
            total_flow_rate = cls._do_flow_rate(dhw_objs, zone.area)
            water_schedule = cls._do_water_schedule(dhw_objs, zone.idf)
            water_schedule.quantity = total_flow_rate
            inlet_temp = cls._do_inlet_temp(dhw_objs, zone.idf)
            supply_temp = cls._do_hot_temp(dhw_objs, zone.idf)

            name = zone.Name + "_DHW"
            z_dhw = cls(
                Name=name,
                Zone=zone,
                FlowRatePerFloorArea=total_flow_rate,
                IsOn=total_flow_rate > 0,
                WaterSchedule=water_schedule,
                WaterSupplyTemperature=supply_temp,
                WaterTemperatureInlet=inlet_temp,
                idf=zone.idf,
                Category=zone.idf.name,
                **kwargs,
            )
            return z_dhw
        else:
            log(f"No 'Water Systems' found in zone '{zone.Name}'")
            return None

    @classmethod
    @timeit
    def _do_hot_temp(cls, dhw_objs, idf):
        """
        Args:
            dhw_objs:
            idf:
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

            hot_schd = UmiSchedule(Name=schedule_name, idf=idf)
            hot_schds.append(hot_schd)

        return np.array([sched.all_values.mean() for sched in hot_schds]).mean()

    @classmethod
    @timeit
    def _do_inlet_temp(cls, dhw_objs, idf):
        """Reference to the Schedule object specifying the cold water
        temperature [C] from the supply mains that provides the cold water to
        the tap and makes up for all water lost down the drain.

        Args:
            dhw_objs:
            idf:
        """
        WaterTemperatureInlet = []
        for obj in dhw_objs:
            if obj.Cold_Water_Supply_Temperature_Schedule_Name != "":
                # If a cold water supply schedule is provided, create the
                # schedule
                cold_schd_names = UmiSchedule(
                    Name=obj.Cold_Water_Supply_Temperature_Schedule_Name, idf=idf
                )
                WaterTemperatureInlet.append(cold_schd_names.mean)
            else:
                # If blank, water temperatures are calculated by the
                # Site:WaterMainsTemperature object.
                water_mains_temps = idf.idfobjects["Site:WaterMainsTemperature".upper()]
                if water_mains_temps:
                    # If a "Site:WaterMainsTemperature" object exists,
                    # do water depending on calc method:
                    water_mains_temp = water_mains_temps[0]
                    if water_mains_temp.Calculation_Method.lower() == "schedule":
                        # From Schedule method
                        mains_scd = UmiSchedule(
                            Name=water_mains_temp.Schedule_Name, idf=idf
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
        return mean(WaterTemperatureInlet) if WaterTemperatureInlet else 10

    @classmethod
    @timeit
    def _do_water_schedule(cls, dhw_objs, idf):
        """Returns the WaterSchedule for a list of WaterUse:Equipment objects.
        If more than one objects are passed, a combined schedule is returned

        Args:
            dhw_objs:
            idf:
        Returns:
            UmiSchedule: The WaterSchedule
        """
        water_schds = [
            UmiSchedule(
                Name=obj.Flow_Rate_Fraction_Schedule_Name,
                idf=idf,
                quantity=obj.Peak_Flow_Rate,
            )
            for obj in dhw_objs
        ]

        return reduce(
            UmiSchedule.combine,
            water_schds,
            weights=None,
            quantity=lambda x: sum(obj.quantity for obj in x),
        )

    @classmethod
    @timeit
    def _do_flow_rate(cls, dhw_objs, area):
        """Calculate total flow rate from list of WaterUse:Equipment objects.
        The zone's net_conditioned_building_area property is used to normalize the flow rate.

        Args:
            dhw_objs (Idf_MSequence):
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
                getattr(self.Zone, str(zone_weight)),
                getattr(other.Zone, str(zone_weight)),
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
            WaterSchedule=UmiSchedule.combine(
                self.WaterSchedule,
                other.WaterSchedule,
                quantity=True,
            ),
            FlowRatePerFloorArea=self._float_mean(
                other, "FlowRatePerFloorArea", weights
            ),
            WaterSupplyTemperature=self._float_mean(
                other, "WaterSupplyTemperature", weights
            ),
            WaterTemperatureInlet=self._float_mean(
                other, "WaterTemperatureInlet", weights
            ),
            idf=self.idf,
        )
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def validate(self):
        """Validate object and fill in missing values."""
        # Assume water systems for whole building
        pass

    @classmethod
    def whole_building(cls, idf):
        z_dhw_list = []
        dhw_objs = idf.idfobjects["WaterUse:Equipment".upper()]

        # Unconditioned area could be zero, therefore taking max of both
        area = max(idf.net_conditioned_building_area, idf.unconditioned_building_area)

        total_flow_rate = DomesticHotWaterSetting._do_flow_rate(dhw_objs, area)
        water_schedule = DomesticHotWaterSetting._do_water_schedule(dhw_objs, idf)
        inlet_temp = DomesticHotWaterSetting._do_inlet_temp(dhw_objs, idf)
        supply_temp = DomesticHotWaterSetting._do_hot_temp(dhw_objs, idf)
        z_dhw = DomesticHotWaterSetting(
            Name="Whole Building WaterUse:Equipment",
            FlowRatePerFloorArea=total_flow_rate,
            IsOn=total_flow_rate > 0,
            WaterSchedule=water_schedule,
            WaterSupplyTemperature=supply_temp,
            WaterTemperatureInlet=inlet_temp,
            idf=idf,
            Category=idf.name,
        )
        z_dhw_list.append(z_dhw)
        if not dhw_objs:
            # defaults with 0 flow rate.
            total_flow_rate = 0
            water_schedule = UmiSchedule.constant_schedule(idf=idf)
            supply_temp = 60
            inlet_temp = 10

            name = idf.name + "_DHW"
            z_dhw = DomesticHotWaterSetting(
                Name=name,
                FlowRatePerFloorArea=total_flow_rate,
                IsOn=total_flow_rate > 0,
                WaterSchedule=water_schedule,
                WaterSupplyTemperature=supply_temp,
                WaterTemperatureInlet=inlet_temp,
                idf=idf,
                Category=idf.name,
            )
            z_dhw_list.append(z_dhw)

        return reduce(DomesticHotWaterSetting.combine, z_dhw_list, weights=[1, 1])

    def mapping(self):
        self.validate()

        return dict(
            FlowRatePerFloorArea=self.FlowRatePerFloorArea,
            IsOn=self.IsOn,
            WaterSchedule=self.WaterSchedule,
            WaterSupplyTemperature=self.WaterSupplyTemperature,
            WaterTemperatureInlet=self.WaterTemperatureInlet,
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
                    for value in DomesticHotWaterSetting.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )


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
