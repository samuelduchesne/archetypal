"""archetypal DomesticHotWaterSetting."""

import collections
from statistics import mean

import numpy as np
from eppy import modeleditor
from sigfig import round
from validator_collection import validators

from archetypal import settings
from archetypal.template.schedule import UmiSchedule
from archetypal.template.umi_base import UmiBase
from archetypal.utils import log, reduce, timeit


class DomesticHotWaterSetting(UmiBase):
    """Domestic Hot Water settings.

    .. image:: ../images/template/zoneinfo-dhw.png
    """

    __slots__ = (
        "_flow_rate_per_floor_area",
        "_is_on",
        "_water_schedule",
        "_water_supply_temperature",
        "_water_temperature_inlet",
        "_area",
    )

    def __init__(
        self,
        Name,
        WaterSchedule=None,
        IsOn=True,
        FlowRatePerFloorArea=0.03,
        WaterSupplyTemperature=65,
        WaterTemperatureInlet=10,
        area=1,
        **kwargs,
    ):
        """Initialize object with parameters.

        Args:
            area (float): The area the zone associated to this object.
            IsOn (bool): If True, dhw is on.
            WaterSchedule (UmiSchedule): Schedule that modulates the
                FlowRatePerFloorArea.
            FlowRatePerFloorArea (float): The flow rate per flow area [m³/(hr·m²)].
            WaterSupplyTemperature (float): The water supply temperature [degC].
            WaterTemperatureInlet (float): The water temperature intel from the water
                mains [degC].
            **kwargs: keywords passed to parent constructors.
        """
        super(DomesticHotWaterSetting, self).__init__(Name, **kwargs)
        self.FlowRatePerFloorArea = FlowRatePerFloorArea
        self.IsOn = IsOn
        self.WaterSupplyTemperature = WaterSupplyTemperature
        self.WaterTemperatureInlet = WaterTemperatureInlet
        self.WaterSchedule = WaterSchedule
        self.area = area

    @property
    def FlowRatePerFloorArea(self):
        """Get or set the flow rate per flow area [m³/(hr·m²)]."""
        return self._flow_rate_per_floor_area

    @FlowRatePerFloorArea.setter
    def FlowRatePerFloorArea(self, value):
        self._flow_rate_per_floor_area = validators.float(value, minimum=0)

    @property
    def IsOn(self):
        """Get or set the availability of the domestic hot water [bool]."""
        return self._is_on

    @IsOn.setter
    def IsOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsOn must "
            f"be a boolean, not a {type(value)}"
        )
        self._is_on = value

    @property
    def WaterSchedule(self):
        """Get or set the schedule which modulates the FlowRatePerFloorArea."""
        return self._water_schedule

    @WaterSchedule.setter
    def WaterSchedule(self, value):
        if value is not None:
            assert isinstance(value, UmiSchedule), (
                f"Input error with value {value}. WaterSchedule must "
                f"be an UmiSchedule, not a {type(value)}"
            )
        self._water_schedule = value

    @property
    def WaterSupplyTemperature(self):
        """Get or set the water supply temperature [degC]."""
        return self._water_supply_temperature

    @WaterSupplyTemperature.setter
    def WaterSupplyTemperature(self, value):
        self._water_supply_temperature = validators.float(value)

    @property
    def WaterTemperatureInlet(self):
        """Get or set the water temperature intel from the water mains [degC]."""
        return self._water_temperature_inlet

    @WaterTemperatureInlet.setter
    def WaterTemperatureInlet(self, value):
        self._water_temperature_inlet = validators.float(value)

    @property
    def area(self):
        """Get or set the area of the zone associated to this object [m²]."""
        return self._area

    @area.setter
    def area(self, value):
        self._area = validators.float(value, minimum=0)

    @classmethod
    def from_dict(cls, data, schedules, **kwargs):
        """Create a DomesticHotWaterSetting from a dictionary.

        Args:
            data (dict): The python dictionary.
            schedules (dict): A dictionary of UmiSchedules with their id as keys.
            **kwargs: keywords passed the MaterialBase constructor.
        """
        _id = data.pop("$id")
        wat_sch = data.pop("WaterSchedule", None)
        schedule = schedules[wat_sch["$ref"]]
        return cls(id=_id, WaterSchedule=schedule, **data, **kwargs)

    def to_dict(self):
        """Return DomesticHotWaterSetting dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["FlowRatePerFloorArea"] = round(self.FlowRatePerFloorArea, sigfigs=4)
        data_dict["IsOn"] = self.IsOn
        data_dict["WaterSchedule"] = self.WaterSchedule.to_ref()
        data_dict["WaterSupplyTemperature"] = round(
            self.WaterSupplyTemperature, sigfigs=4
        )
        data_dict["WaterTemperatureInlet"] = round(
            self.WaterTemperatureInlet, sigfigs=4
        )
        data_dict["Category"] = self.Category
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    @timeit
    def from_zone(cls, zone_epbunch, **kwargs):
        """Create object from a zone EpBunch.

        WaterUse:Equipment objects referring to this zone will be parsed.

        Args:
            zone (EpBunch): The zone object.
        """
        # If Zone is not part of Conditioned Area, it should not have a DHW object.
        if zone_epbunch.Part_of_Total_Floor_Area.lower() == "no":
            return None

        # First, find the WaterUse:Equipment assigned to this zone
        dhw_objs = zone_epbunch.getreferingobjs(
            iddgroups=["Water Systems"], fields=["Zone_Name"]
        )
        if not dhw_objs:
            # Sometimes, some of the WaterUse:Equipment objects are not assigned to
            # any zone. Therefore, to account for their water usage, we can try to
            # assign dangling WaterUse:Equipments by looking for the zone name in the
            # object name.
            dhw_objs.extend(
                [
                    dhw
                    for dhw in zone_epbunch.theidf.idfobjects["WATERUSE:EQUIPMENT"]
                    if zone_epbunch.Name.lower() in dhw.Name.lower()
                ]
            )

        if dhw_objs:
            # This zone has more than one WaterUse:Equipment object
            zone_area = modeleditor.zonearea(zone_epbunch.theidf, zone_epbunch.Name)
            total_flow_rate = cls._do_flow_rate(dhw_objs, zone_area)
            water_schedule = cls._do_water_schedule(dhw_objs)
            inlet_temp = cls._do_inlet_temp(dhw_objs)
            supply_temp = cls._do_hot_temp(dhw_objs)

            name = zone_epbunch.Name + "_DHW"
            z_dhw = cls(
                Name=name,
                FlowRatePerFloorArea=total_flow_rate,
                IsOn=bool(total_flow_rate > 0),
                WaterSchedule=water_schedule,
                WaterSupplyTemperature=supply_temp,
                WaterTemperatureInlet=inlet_temp,
                Category=zone_epbunch.theidf.name,
                area=zone_area,
                **kwargs,
            )
            return z_dhw
        else:
            log(f"No 'Water Systems' found in zone '{zone_epbunch.Name}'")
            return None

    @classmethod
    def _do_hot_temp(cls, dhw_objs):
        """Resolve hot water temperature.

        Args:
            dhw_objs:
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
            epbunch = obj.theidf.schedules_dict[schedule_name.upper()]
            hot_schd = UmiSchedule.from_epbunch(epbunch)
            hot_schds.append(hot_schd)

        return np.array([sched.all_values.mean() for sched in hot_schds]).mean()

    @classmethod
    def _do_inlet_temp(cls, dhw_objs):
        """Calculate inlet water temperature."""
        WaterTemperatureInlet = []
        for obj in dhw_objs:
            if obj.Cold_Water_Supply_Temperature_Schedule_Name != "":
                # If a cold water supply schedule is provided, create the
                # schedule
                epbunch = obj.theidf.schedules_dict[
                    obj.Cold_Water_Supply_Temperature_Schedule_Name.upper()
                ]
                cold_schd_names = UmiSchedule.from_epbunch(epbunch)
                WaterTemperatureInlet.append(cold_schd_names.mean)
            else:
                # If blank, water temperatures are calculated by the
                # Site:WaterMainsTemperature object.
                water_mains_temps = obj.theidf.idfobjects[
                    "Site:WaterMainsTemperature".upper()
                ]
                if water_mains_temps:
                    # If a "Site:WaterMainsTemperature" object exists,
                    # do water depending on calc method:
                    water_mains_temp = water_mains_temps[0]
                    if water_mains_temp.Calculation_Method.lower() == "schedule":
                        # From Schedule method
                        mains_scd = UmiSchedule.from_epbunch(
                            obj.theidf.schedules_dict[
                                water_mains_temp.Schedule_Name.upper()
                            ]
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
    def _do_water_schedule(cls, dhw_objs):
        """Return the WaterSchedule for a list of WaterUse:Equipment objects.

        If more than one objects are passed, a combined schedule is returned

        Args:
            dhw_objs (list of EpBunch): List of WaterUse:Equipment objects.

        Returns:
            UmiSchedule: The WaterSchedule
        """
        water_schds = [
            UmiSchedule.from_epbunch(
                obj.theidf.schedules_dict[obj.Flow_Rate_Fraction_Schedule_Name.upper()],
                quantity=obj.Peak_Flow_Rate,
            )
            for obj in dhw_objs
        ]

        return reduce(
            UmiSchedule.combine,
            water_schds,
            weights=None,
            quantity=True,
        )

    @classmethod
    def _do_flow_rate(cls, dhw_objs, area):
        """Calculate total flow rate from list of WaterUse:Equipment objects.

        The zone's net_conditioned_building_area property is used to normalize the
        flow rate.

        Args:
            dhw_objs (Idf_MSequence):
        """
        total_flow_rate = 0
        for obj in dhw_objs:
            total_flow_rate += obj.Peak_Flow_Rate  # m3/s
        total_flow_rate /= area  # m3/s/m2
        total_flow_rate *= 3600.0  # m3/h/m2
        return total_flow_rate

    def combine(self, other, **kwargs):
        """Combine two DomesticHotWaterSetting objects together.

        Notes:
            When combining 2 DomesticHotWater Settings objects, the WaterSchedule
            must be averaged via the final quantity which is the peak floor rate
            [m3/hr/m2] * area [m2].

        .. code-block:: python

            (
                np.average(
                    [zone_1.WaterSchedule.all_values, zone_2.WaterSchedule.all_values],
                    axis=0,
                    weights=[
                        zone_1.FlowRatePerFloorArea * zone_1.area,
                        zone_2.FlowRatePerFloorArea * zone_2.area,
                    ],
                )
                * (combined.FlowRatePerFloorArea * 100)
            ).sum()

        Args:
            other (DomesticHotWaterSetting): The other object.
            **kwargs: keywords passed to the constructor.

        Returns:
            (DomesticHotWaterSetting): a new combined object.
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
        new_obj = DomesticHotWaterSetting(
            WaterSchedule=UmiSchedule.combine(
                self.WaterSchedule,
                other.WaterSchedule,
                weights=[
                    self.FlowRatePerFloorArea * self.area,
                    other.FlowRatePerFloorArea * other.area,
                ],
            ),
            IsOn=any((self.IsOn, other.IsOn)),
            FlowRatePerFloorArea=self.float_mean(
                other, "FlowRatePerFloorArea", [self.area, other.area]
            ),
            WaterSupplyTemperature=self.float_mean(
                other, "WaterSupplyTemperature", [self.area, other.area]
            ),
            WaterTemperatureInlet=self.float_mean(
                other, "WaterTemperatureInlet", [self.area, other.area]
            ),
            area=self.area + other.area,
            **meta,
        )
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def validate(self):
        """Validate object and fill in missing values."""
        return self

    @classmethod
    def whole_building(cls, idf):
        """Create one DomesticHotWaterSetting for whole building model.

        Args:
            idf (IDF): The idf model.

        Returns:
            DomesticHotWaterSetting: The DomesticHotWaterSetting object.
        """
        # Unconditioned area could be zero, therefore taking max of both
        area = max(idf.net_conditioned_building_area, idf.unconditioned_building_area)

        z_dhw_list = []
        dhw_objs = idf.idfobjects["WaterUse:Equipment".upper()]
        if not dhw_objs:
            # defaults with 0 flow rate.
            total_flow_rate = 0
            water_schedule = UmiSchedule.constant_schedule()
            supply_temp = 60
            inlet_temp = 10

            name = idf.name + "_DHW"
            z_dhw = DomesticHotWaterSetting(
                WaterSchedule=water_schedule,
                IsOn=bool(total_flow_rate > 0),
                FlowRatePerFloorArea=total_flow_rate,
                WaterSupplyTemperature=supply_temp,
                WaterTemperatureInlet=inlet_temp,
                area=area,
                Name=name,
                Category=idf.name,
            )
            z_dhw_list.append(z_dhw)
        else:
            total_flow_rate = DomesticHotWaterSetting._do_flow_rate(dhw_objs, area)
            water_schedule = DomesticHotWaterSetting._do_water_schedule(dhw_objs)
            water_schedule.quantity = total_flow_rate
            inlet_temp = DomesticHotWaterSetting._do_inlet_temp(dhw_objs)
            supply_temp = DomesticHotWaterSetting._do_hot_temp(dhw_objs)
            z_dhw = DomesticHotWaterSetting(
                WaterSchedule=water_schedule,
                IsOn=bool(total_flow_rate > 0),
                FlowRatePerFloorArea=total_flow_rate,
                WaterSupplyTemperature=supply_temp,
                WaterTemperatureInlet=inlet_temp,
                area=area,
                Name="Whole Building WaterUse:Equipment",
                Category=idf.name,
            )
            z_dhw_list.append(z_dhw)

        return reduce(DomesticHotWaterSetting.combine, z_dhw_list)

    def mapping(self, validate=True):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
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

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other (DomesticHotWaterSetting):
        """
        return self.combine(
            other,
        )

    def __hash__(self):
        """Return the hash value of self."""
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __key__(self):
        """Get a tuple of attributes. Useful for hashing and comparing."""
        return (
            self.IsOn,
            self.FlowRatePerFloorArea,
            self.WaterSupplyTemperature,
            self.WaterTemperatureInlet,
            self.WaterSchedule,
        )

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, DomesticHotWaterSetting):
            return NotImplemented
        else:
            return self.__key__() == other.__key__()

    def __str__(self):
        """Return string representation."""
        return (
            f"{str(self.id)}: {str(self.Name)} "
            f"PeakFlow {self.FlowRatePerFloorArea:.5f} m3/hr/m2"
        )

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(**self.mapping(validate=False))


def water_main_correlation(t_out_avg, max_diff):
    """Based on the correlation developed by Craig Christensen and Jay Burch.

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

    def function(t_out_avg, day, max_diff):
        return (t_out_avg + 6) + ratio * (max_diff / 2) * np.sin(
            np.deg2rad(0.986 * (day - 15 - lag) - 90)
        )

    mains = [Q_(function(t_out_avg_F.m, day, max_diff_F.m), "degF") for day in days]
    series = pd.Series([temp.to("degC").m for temp in mains])
    return series
