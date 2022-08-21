from sqlite3 import connect

import numpy as np
import pandas as pd
from energy_pandas import EnergyDataFrame
from energy_pandas.units import unit_registry

from archetypal.idfclass.sql import Sql


class EndUseBalance:
    HVAC_MODE = ("Zone Predicted Sensible Load to Setpoint Heat Transfer Rate",)
    HVAC_INPUT_SENSIBLE = (  # not multiplied by zone or group multipliers
        "Zone Air Heat Balance System Air Transfer Rate",
        "Zone Air Heat Balance System Convective Heat Gain Rate",
    )
    HVAC_INPUT_HEATED_SURFACE = (
        "Zone Radiant HVAC Heating Energy",
        "Zone Ventilated Slab Radiant Heating Energy",
    )
    HVAC_INPUT_COOLED_SURFACE = (
        "Zone Radiant HVAC Cooling Energy",
        "Zone Ventilated Slab Radiant Cooling Energy",
    )
    LIGHTING = ("Zone Lights Total Heating Energy",)  # checked
    EQUIP_GAINS = (  # checked
        "Zone Electric Equipment Radiant Heating Energy",
        "Zone Gas Equipment Radiant Heating Energy",
        "Zone Steam Equipment Radiant Heating Energy",
        "Zone Hot Water Equipment Radiant Heating Energy",
        "Zone Other Equipment Radiant Heating Energy",
        "Zone Electric Equipment Convective Heating Energy",
        "Zone Gas Equipment Convective Heating Energy",
        "Zone Steam Equipment Convective Heating Energy",
        "Zone Hot Water Equipment Convective Heating Energy",
        "Zone Other Equipment Convective Heating Energy",
    )
    PEOPLE_GAIN = ("Zone People Total Heating Energy",)  # checked
    SOLAR_GAIN = ("Zone Windows Total Transmitted Solar Radiation Energy",)  # checked
    INFIL_GAIN = (
        "Zone Infiltration Total Heat Gain Energy",  # checked
        "AFN Zone Infiltration Total Heat Gain Energy",
    )
    INFIL_LOSS = (
        "Zone Infiltration Total Heat Loss Energy",  # checked
        "AFN Zone Infiltration Total Heat Loss Energy",
    )
    VENTILATION_LOSS = ("Zone Air System Total Heating Energy",)
    VENTILATION_GAIN = ("Zone Air System Total Cooling Energy",)
    NAT_VENT_GAIN = (
        "Zone Ventilation Total Heat Gain Energy",
        "AFN Zone Ventilation Total Heat Gain Energy",
    )
    NAT_VENT_LOSS = (
        "Zone Ventilation Total Heat Loss Energy",
        "AFN Zone Ventilation Total Heat Loss Energy",
    )
    OPAQUE_ENERGY_FLOW = ("Surface Outside Face Conduction Heat Transfer Energy",)
    OPAQUE_ENERGY_STORAGE = ("Surface Heat Storage Energy",)
    WINDOW_LOSS = ("Zone Windows Total Heat Loss Energy",)  # checked
    WINDOW_GAIN = ("Zone Windows Total Heat Gain Energy",)  # checked
    HRV_LOSS = ("Heat Exchanger Total Cooling Energy",)
    HRV_GAIN = ("Heat Exchanger Total Heating Energy",)
    AIR_SYSTEM = (
        "Air System Heating Coil Total Heating Energy",
        "Air System Cooling Coil Total Cooling Energy",
    )

    def __init__(
        self,
        sql_file,
        cooling,
        heating,
        lighting,
        electric_equip,
        gas_equip,
        how_water,
        people_gain,
        solar_gain,
        infiltration,
        mech_vent,
        nat_vent,
        window_energy_flow,
        opaque_flow,
        opaque_storage,
        window_flow,
        heat_recovery,
        air_system,
        is_cooling,
        is_heating,
        units="J",
        use_all_solar=True,
    ):
        self.sql_file = sql_file
        self.cooling = cooling
        self.heating = heating
        self.lighting = lighting
        self.electric_equip = electric_equip
        self.gas_equip = gas_equip
        self.hot_water = how_water
        self.people_gain = people_gain
        self.solar_gain = solar_gain
        self.infiltration = infiltration
        self.mech_vent = mech_vent
        self.nat_vent = nat_vent
        self.window_energy_flow = window_energy_flow
        self.opaque_flow = opaque_flow
        self.opaque_storage = opaque_storage
        self.window_flow = window_flow
        self.heat_recovery = heat_recovery
        self.air_system = air_system
        self.units = units
        self.use_all_solar = use_all_solar
        self.is_cooling = is_cooling
        self.is_heating = is_heating

    @classmethod
    def from_sql_file(
        cls, sql_file, units="kWh", power_units="kW", outdoor_surfaces_only=True
    ):
        sql = Sql(sql_file)

        _hvac_input = sql.timeseries_by_name(cls.HVAC_INPUT_SENSIBLE).to_units(
            power_units
        )
        _hvac_input_heated_surface = sql.timeseries_by_name(
            cls.HVAC_INPUT_HEATED_SURFACE
        ).to_units(units)
        _hvac_input_cooled_surface = sql.timeseries_by_name(
            cls.HVAC_INPUT_COOLED_SURFACE
        ).to_units(units)
        # convert power to energy assuming the reporting frequency
        freq = pd.infer_freq(_hvac_input.index)
        assert freq == "H", "A reporting frequency other than H is not yet supported."
        freq_to_unit = {"H": "hr"}
        _hvac_input = _hvac_input.apply(
            lambda row: unit_registry.Quantity(
                row.values,
                unit_registry(power_units) * unit_registry(freq_to_unit[freq]),
            )
            .to(units)
            .m
        )

        _hvac_input = pd.concat(
            filter(
                lambda x: not x.empty,
                [
                    _hvac_input,
                    EndUseBalance.subtract_cooled_from_heated_surface(
                        _hvac_input_cooled_surface, _hvac_input_heated_surface
                    ),
                ],
            ),
            axis=1,
            verify_integrity=True,
        )
        mode = sql.timeseries_by_name(cls.HVAC_MODE)  # positive = Heating
        rolling_sign = cls.get_rolling_sign_change(mode).fillna(0)

        # Create both heating and cooling masks
        is_heating = rolling_sign.droplevel(["IndexGroup", "Name"], axis=1) == 1
        is_cooling = rolling_sign.droplevel(["IndexGroup", "Name"], axis=1) == -1

        heating = _hvac_input.mul(is_heating, level="KeyValue", axis=1)
        cooling = _hvac_input.mul(is_cooling, level="KeyValue", axis=1)

        lighting = sql.timeseries_by_name(cls.LIGHTING).to_units(units)
        zone_multipliers = sql.zone_info.set_index("ZoneName")["Multiplier"].rename(
            "KeyValue"
        )
        lighting = cls.apply_multipliers(
            lighting,
            zone_multipliers,
        )
        people_gain = sql.timeseries_by_name(cls.PEOPLE_GAIN).to_units(units)
        people_gain = cls.apply_multipliers(people_gain, zone_multipliers)
        equipment = sql.timeseries_by_name(cls.EQUIP_GAINS).to_units(units)
        equipment = cls.apply_multipliers(equipment, zone_multipliers)
        solar_gain = sql.timeseries_by_name(cls.SOLAR_GAIN).to_units(units)
        solar_gain = cls.apply_multipliers(solar_gain, zone_multipliers)
        infil_gain = sql.timeseries_by_name(cls.INFIL_GAIN).to_units(units)
        infil_gain = cls.apply_multipliers(infil_gain, zone_multipliers)
        infil_loss = sql.timeseries_by_name(cls.INFIL_LOSS).to_units(units)
        infil_loss = cls.apply_multipliers(infil_loss, zone_multipliers)
        vent_loss = sql.timeseries_by_name(cls.VENTILATION_LOSS).to_units(units)
        vent_loss = cls.apply_multipliers(vent_loss, zone_multipliers)
        vent_gain = sql.timeseries_by_name(cls.VENTILATION_GAIN).to_units(units)
        vent_gain = cls.apply_multipliers(vent_gain, zone_multipliers)
        nat_vent_gain = sql.timeseries_by_name(cls.NAT_VENT_GAIN).to_units(units)
        nat_vent_gain = cls.apply_multipliers(nat_vent_gain, zone_multipliers)
        nat_vent_loss = sql.timeseries_by_name(cls.NAT_VENT_LOSS).to_units(units)
        nat_vent_loss = cls.apply_multipliers(nat_vent_loss, zone_multipliers)
        hrv_loss = sql.timeseries_by_name(cls.HRV_LOSS).to_units(units)
        hrv_gain = sql.timeseries_by_name(cls.HRV_GAIN).to_units(units)
        hrv = cls.subtract_loss_from_gain(hrv_gain, hrv_loss, level="KeyValue")
        air_system = sql.timeseries_by_name(cls.AIR_SYSTEM).to_units(units)

        # subtract losses from gains
        infiltration = None
        mech_vent = None
        nat_vent = None
        if len(infil_gain) == len(infil_loss):
            infiltration = cls.subtract_loss_from_gain(
                infil_gain, infil_loss, level="Name"
            )
        if nat_vent_gain.shape == nat_vent_loss.shape:
            nat_vent = cls.subtract_loss_from_gain(
                nat_vent_gain, nat_vent_loss, level="Name"
            )

        # get the surface energy flow
        opaque_flow = sql.timeseries_by_name(cls.OPAQUE_ENERGY_FLOW).to_units(units)
        opaque_storage = sql.timeseries_by_name(cls.OPAQUE_ENERGY_STORAGE).to_units(
            units
        )
        opaque_storage_ = opaque_storage.copy()
        opaque_storage_.columns = opaque_flow.columns
        opaque_flow = -(opaque_flow + opaque_storage_)
        window_loss = sql.timeseries_by_name(cls.WINDOW_LOSS).to_units(units)
        window_loss = cls.apply_multipliers(window_loss, zone_multipliers)
        window_gain = sql.timeseries_by_name(cls.WINDOW_GAIN).to_units(units)
        window_gain = cls.apply_multipliers(window_gain, zone_multipliers)
        window_flow = cls.subtract_loss_from_gain(
            window_gain, window_loss, level="Name"
        )
        window_flow = cls.subtract_solar_from_window_net(
            window_flow, solar_gain, level="KeyValue"
        )

        opaque_flow = cls.match_opaque_surface_to_zone(
            sql.surfaces_table, opaque_flow, sql.zone_info
        )
        opaque_storage = cls.match_opaque_surface_to_zone(
            sql.surfaces_table, opaque_storage, sql.zone_info
        )
        if outdoor_surfaces_only:
            # inside surfaces are identified by ExtBoundCond > 0
            inside_surfaces = sql.surfaces_table[lambda x: x["ExtBoundCond"] > 0][
                "SurfaceName"
            ].values.tolist()

            # drop inside surfaces
            opaque_flow = opaque_flow.drop(
                inside_surfaces, level="KeyValue", axis=1, errors="ignore"
            )
            opaque_storage = opaque_storage.drop(
                inside_surfaces, level="KeyValue", axis=1, errors="ignore"
            )
        window_energy_flow = window_flow

        bal_obj = cls(
            sql_file,
            cooling,
            heating,
            lighting,
            equipment,
            None,
            None,
            people_gain,
            solar_gain,
            infiltration,
            mech_vent,
            nat_vent,
            window_energy_flow,
            opaque_flow,
            opaque_storage,
            window_flow,
            hrv,
            air_system,
            is_cooling,
            is_heating,
            units,
            use_all_solar=True,
        )
        return bal_obj

    @classmethod
    def apply_multipliers(cls, data, idf):
        from archetypal import IDF

        if isinstance(idf, IDF):
            multipliers = (
                pd.Series(
                    {
                        zone.Name.upper(): zone.Multiplier
                        for zone in idf.idfobjects["ZONE"]
                    },
                    name="Key_Name",
                )
                .replace({"": 1})
                .fillna(1)
            )
            key = "OutputVariable"
        elif isinstance(idf, pd.Series):
            multipliers = idf
            key = "KeyValue"
        else:
            raise ValueError
        return data.mul(multipliers, level=key, axis=1)

    @classmethod
    def subtract_cooled_from_heated_surface(
        cls, _hvac_input_cooled_surface, _hvac_input_heated_surface
    ):
        if _hvac_input_cooled_surface.empty:
            return _hvac_input_cooled_surface
        try:
            columns = _hvac_input_heated_surface.rename(
                columns=lambda x: str.replace(x, " Heating", ""), level="OutputVariable"
            ).columns
        except KeyError:
            columns = None
        return EnergyDataFrame(
            (
                _hvac_input_heated_surface.sum(level="KeyValue", axis=1)
                - _hvac_input_cooled_surface.sum(level="KeyValue", axis=1)
            ).values,
            columns=columns,
            index=_hvac_input_heated_surface.index,
        )

    @classmethod
    def get_rolling_sign_change(cls, data: pd.DataFrame):
        # create a sign series where -1 is negative and 0 or 1 is positive
        sign = (
            np.sign(data)
            .replace({0: np.NaN})
            .fillna(method="bfill")
            .fillna(method="ffill")
        )
        # when does a change of sign occurs?
        sign_switch = sign != sign.shift(-1)
        # From sign, keep when the sign switches and fill with the previous values
        # (back fill). The final forward fill is to fill the last few timesteps of the
        # series which might be NaNs.
        rolling_sign = sign[sign_switch].fillna(method="bfill").fillna(method="ffill")
        return rolling_sign

    @classmethod
    def match_window_to_zone(cls, idf, window_flow):
        """Match window surfaces with their wall and zone.

        Adds the following properties to the `window_flow` DataFrame as a MultiIndex level with names:
            * Building_Surface_Name
            * Surface_Type
            * Zone_Name
            * Multiplier
        """
        # Todo: Check if Zone Multiplier needs to be added.
        assert window_flow.columns.names == ["OutputVariable", "Key_Name"]
        window_to_surface_match = pd.DataFrame(
            [
                (
                    window.Name.upper(),  # name of the window
                    window.Building_Surface_Name.upper(),  # name of the wall this window is on
                    window.get_referenced_object(
                        "Building_Surface_Name"
                    ).Surface_Type.title(),  # surface type (wall, ceiling, floor) this windows is on.
                    window.get_referenced_object(  # get the zone name though the surface name
                        "Building_Surface_Name"
                    ).Zone_Name.upper(),
                    float(window.Multiplier)
                    if window.Multiplier != ""
                    else 1,  # multiplier of this window.
                )
                for window in idf.getsubsurfaces()
            ],
            columns=[
                "Name",
                "Building_Surface_Name",
                "Surface_Type",
                "Zone_Name",
                "Multiplier",
            ],
        ).set_index("Name")
        # Match the subsurface to the surface name and the zone name it belongs to.
        stacked = (
            window_flow.stack()
            .join(
                window_to_surface_match.rename(index=str.upper),
                on="Key_Name",
            )
            .set_index(
                ["Building_Surface_Name", "Surface_Type", "Zone_Name"], append=True
            )
        )
        window_flow = (
            stacked.drop(columns=["Multiplier"]).iloc[:, 0] * stacked["Multiplier"]
        )
        window_flow = window_flow.unstack(
            level=["Key_Name", "Building_Surface_Name", "Surface_Type", "Zone_Name"]
        )

        return window_flow  # .groupby("Building_Surface_Name", axis=1).sum()

    @classmethod
    def match_opaque_surface_to_zone(cls, surface_table, opaque_flow, zone_info):
        """Match opaque surfaces with their zone.

        Multiplies the surface heat flow by the zone multiplier.

        Adds the following properties to the `opaque_flow` DataFrame as a MultiIndex level with names:
            * Surface_Type
            * Outside_Boundary_Condition
            * Zone_Name
        """
        surface_with_idx = surface_table.join(
            zone_info["ZoneName"], on="ZoneIndex"
        ).reset_index()
        opaque_flow.columns = pd.MultiIndex.from_frame(
            opaque_flow.columns.to_frame(index=False).join(
                surface_with_idx.reset_index()
                .set_index("SurfaceName")[
                    ["ClassName", "ExtBoundCond", "ZoneName", "ZoneIndex"]
                ]
                .rename(
                    {
                        "ClassName": "Surface_Type",
                        "ExtBoundCond": "Outside_Boundary_Condition",
                        "ZoneName": "Zone_Name",
                    },
                    axis=1,
                ),
                on="KeyValue",
            )
        )
        opaque_flow.mul(zone_info["Multiplier"], level="ZoneIndex")
        opaque_flow = opaque_flow.droplevel("ZoneIndex", axis=1)
        return opaque_flow

    @classmethod
    def subtract_loss_from_gain(cls, load_gain, load_loss, level="OutputVariable"):
        try:
            columns = load_gain.rename(
                columns=lambda x: str.replace(x, " Gain", ""), level=level
            ).columns
        except KeyError:
            columns = None
        return EnergyDataFrame(
            load_gain.values - load_loss.values,
            columns=columns,
            index=load_gain.index,
        )

    @classmethod
    def subtract_solar_from_window_net(cls, window_flow, solar_gain, level="Key_Name"):
        columns = window_flow.columns
        return EnergyDataFrame(
            (window_flow.sum(level=level, axis=1) - solar_gain.sum(level=level, axis=1))
            .loc[:, list(columns.get_level_values(level))]
            .values,
            columns=columns,
            index=window_flow.index,
        )

    @classmethod
    def subtract_vent_from_system(cls, system, vent, level="Key_Name"):
        columns = vent.columns
        return EnergyDataFrame(
            system.sum(level=level, axis=1).values
            - vent.sum(level=level, axis=1).values,
            columns=columns,
            index=system.index,
        )

    def separate_gains_and_losses(self, component, level="Key_Name") -> EnergyDataFrame:
        """Separate gains from losses when cooling and heating occurs for the component.

        Args:
            component (str):
            level (str or list):

        Returns:

        """
        assert (
            component in self.__dict__.keys()
        ), f"{component} is not a valid attribute of EndUseBalance."
        component_df = getattr(self, component)
        assert not component_df.empty, "Expected a component that is not empty."
        print(component)

        c_df = getattr(self, component)

        # concatenate the Periods
        inter = pd.concat(
            [
                c_df.mul(self.is_cooling.rename_axis(level, axis=1), level=level),
                c_df.mul(self.is_heating.rename_axis(level, axis=1), level=level),
            ],
            keys=["Cooling Periods", "Heating Periods"],
            names=["Period"],
        )

        # mask when values are positive (gain)
        positive_mask = inter >= 0

        # concatenate the Gain/Loss
        final = pd.concat(
            [
                inter[positive_mask].reindex(inter.index),
                inter[~positive_mask].reindex(inter.index),
            ],
            keys=["Heat Gain", "Heat Loss"],
            names=["Gain/Loss"],
        ).unstack(["Period", "Gain/Loss"])
        final.sort_index(axis=1, inplace=True)
        return final

    def to_df(self, separate_gains_and_losses=False, level="KeyValue"):
        """Summarize components into a DataFrame."""
        if separate_gains_and_losses:
            summary_by_component = {}
            levels = ["Component", "Zone_Name", "Period", "Gain/Loss"]
            for component in [
                "cooling",
                "heating",
                "lighting",
                "electric_equip",
                "people_gain",
                "solar_gain",
                "infiltration",
                "window_energy_flow",
                "nat_vent",
            ]:
                if not getattr(self, component).empty:
                    summary_by_component[component] = (
                        self.separate_gains_and_losses(
                            component,
                            level=level,
                        )
                        .groupby(level=["KeyValue", "Period", "Gain/Loss"], axis=1)
                        .sum()
                        .sort_index(axis=1)
                    )
            for (surface_type), data in self.separate_gains_and_losses(
                "opaque_flow", level="Zone_Name"
            ).groupby(level=["Surface_Type"], axis=1):
                summary_by_component[surface_type] = data.sum(
                    level=["Zone_Name", "Period", "Gain/Loss"], axis=1
                ).sort_index(axis=1)

        else:
            summary_by_component = {}
            for component in [
                "cooling",
                "heating",
                "lighting",
                "electric_equip",
                "people_gain",
                "solar_gain",
                "infiltration",
                "window_energy_flow",
                "nat_vent",
            ]:
                component_df = getattr(self, component)
                if not component_df.empty:
                    summary_by_component[component] = component_df.sum(
                        level=level, axis=1
                    ).sort_index(axis=1)
            for (zone_name, surface_type), data in self.opaque_flow.groupby(
                level=["Zone_Name", "Surface_Type"], axis=1
            ):
                summary_by_component[surface_type] = data.sum(
                    level="Zone_Name", axis=1
                ).sort_index(axis=1)
            levels = ["Component", "Zone_Name"]

        # Add contribution of heating/cooling outside air, if any
        if not self.air_system.empty:
            summary_by_component["air_system_heating"] = (
                self.air_system.xs(
                    "Air System Heating Coil Total Heating Energy", level="Name", axis=1
                )
                .assign(**{"Period": "Heating Periods", "Gain/Loss": "Heat Loss"})
                .set_index(["Period", "Gain/Loss"], append=True)
                .unstack(["Period", "Gain/Loss"])
                .droplevel("IndexGroup", axis=1)
            )
            summary_by_component["air_system_cooling"] = (
                self.air_system.xs(
                    "Air System Cooling Coil Total Cooling Energy", level="Name", axis=1
                )
                .assign(**{"Period": "Cooling Periods", "Gain/Loss": "Heat Gain"})
                .set_index(["Period", "Gain/Loss"], append=True)
                .unstack(["Period", "Gain/Loss"])
                .droplevel("IndexGroup", axis=1)
            )
        return pd.concat(
            summary_by_component, axis=1, verify_integrity=True, names=levels
        )

    def component_summary(self) -> EnergyDataFrame:
        """Return a DataFrame of components summarized annually."""
        sum_opaque_flow = (
            self.separate_gains_and_losses("opaque_flow", "Zone_Name")
            .sum()
            .sum(level=["Period", "Gain/Loss"])
        )
        sum_window_flow = (
            self.separate_gains_and_losses("window_flow", "Zone_Name")
            .sum()
            .sum(level=["Period", "Gain/Loss"])
        )
        sum_solar_gain = (
            self.separate_gains_and_losses("solar_gain")
            .sum()
            .sum(level=["Period", "Gain/Loss"])
        )
        sum_lighting = (
            self.separate_gains_and_losses("lighting")
            .sum()
            .sum(level=["Period", "Gain/Loss"])
        )
        sum_infiltration = (
            self.separate_gains_and_losses("infiltration")
            .sum()
            .sum(level=["Period", "Gain/Loss"])
        )
        sum_people_gain = (
            self.separate_gains_and_losses("people_gain")
            .sum()
            .sum(level=["Period", "Gain/Loss"])
        )

        df = pd.concat(
            [
                sum_opaque_flow,
                sum_window_flow,
                sum_solar_gain,
                sum_lighting,
                sum_infiltration,
                sum_people_gain,
            ],
            keys=[
                "Opaque Conduction",
                "Window Conduction",
                "Window Solar Gains",
                "Lighting",
                "Infiltration",
                "Occupants (Sensible + Latent)",
            ],
        )

        return df.unstack(level=["Period", "Gain/Loss"])

    def to_sankey(self, path_or_buf):
        system_data = self.to_df(separate_gains_and_losses=True)
        annual_system_data = system_data.sum().sum(
            level=["Component", "Period", "Gain/Loss"]
        )
        annual_system_data.rename(
            {
                "people_gain": "Occupants",
                "solar_gain": "Passive Solar",
                "electric_equip": "Equipment",
                "lighting": "Lighting",
                "infiltration": "Infiltration",
                "interior_equipment": "Equipment",
                "window_energy_flow": "Windows",
                "Wall": "Walls",
                "air_system_heating": "OA Heating",
                "air_system_cooling": "OA Cooling",
                "cooling": "Cooling",
                "heating": "Heating",
            },
            inplace=True,
        )

        heating_load = annual_system_data.xs("Heating Periods", level="Period")
        cooling_load = annual_system_data.xs("Cooling Periods", level="Period")

        end_uses = (
            "Heating",
            "Cooling",
            "Interior Lighting",
            "Exterior Lighting",
            "Interior Equipment",
            "Exterior Equipment",
            "Fans",
            "Pumps",
            "Heat Rejection",
            "Humidification",
            "Heat Recovery",
            "Water Systems",
            "Refrigeration",
            "Generators",
        )
        energy_sources = (
            "Electricity",
            "Natural Gas",
            "District Cooling",
            "District Heating",
        )
        with connect(self.sql_file) as conn:
            df = pd.read_sql(
                'select * from "TabularDataWithStrings" as f where f."TableName" == "End Uses" and f."ReportName" == "AnnualBuildingUtilityPerformanceSummary"',
                conn,
            )
            system_input = df.pivot(
                index="RowName", columns="ColumnName", values="Value"
            ).loc[end_uses, energy_sources]
            system_input = system_input.astype("float")
            system_input = EnergyDataFrame(
                system_input.values,
                index=system_input.index,
                columns=system_input.columns,
            )
            system_input.units = df.set_index("ColumnName").Units.to_dict()
            system_input = system_input.to_units("kWh")

        floor_area = pd.to_numeric(
            Sql(self.sql_file)
            .tabular_data_by_name(
                *(
                    "AnnualBuildingUtilityPerformanceSummary",
                    "Building Area",
                    "Entire Facility",
                )
            )
            .loc["Net Conditioned Building Area", ("Area", "m2")]
        )

        system_input = (
            system_input.replace({0: np.NaN})
            .dropna(how="all")
            .dropna(how="all", axis=1)
        )
        system_input.rename_axis("source", axis=1, inplace=True)
        system_input.rename_axis("target", axis=0, inplace=True)
        system_input = system_input.unstack().rename("value").reset_index().dropna()
        system_input_data = system_input.to_dict(orient="records")

        heating_energy_to_heating_system = [
            {
                "source": "Heating",
                "target": "Heating System",
                "value": system_input.set_index("target").at["Heating", "value"].sum(),
            }
        ]

        cooling_energy_to_heating_system = [
            {
                "source": "Cooling",
                "target": "Cooling System",
                "value": system_input.set_index("target").at["Cooling", "value"].sum(),
            }
        ]

        (
            heating_load_source_data,
            heating_load_target_data,
            link_heating_system_to_gains,
        ) = self._sankey_heating(heating_load, load_type="heating")

        (
            cooling_load_source_data,
            cooling_load_target_data,
            link_cooling_system_to_gains,
        ) = self._sankey_cooling(cooling_load, load_type="cooling")

        flows = pd.DataFrame(
            system_input_data
            + heating_energy_to_heating_system
            + heating_load_source_data
            + heating_load_target_data
            + cooling_energy_to_heating_system
            + cooling_load_source_data
            + cooling_load_target_data
        )
        # Fix the HVAC difference
        diff = (
            flows.loc[flows.source == "Heating Load", "value"].sum()
            - flows.loc[flows.target == "Heating Load", "value"].sum()
        )
        flows.loc[flows.source == "Heating System", "value"] = (
            flows.loc[flows.source == "Heating System", "value"] + diff
        )

        diff = (
            flows.loc[flows.source == "Cooling Load", "value"].sum()
            - flows.loc[flows.target == "Cooling Load", "value"].sum()
        )
        flows.loc[flows.source == "Cooling System", "value"] = (
            flows.loc[flows.source == "Cooling System", "value"] + diff
        )

        # fix names
        flows.replace({"OA Heating Heat Losses": "OA Heating"}, inplace=True)

        # TO EUI
        flows["value"] = flows["value"] / floor_area
        links = pd.DataFrame(
            link_heating_system_to_gains + link_cooling_system_to_gains
        )
        return pd.concat([flows, links]).to_csv(path_or_buf, index=False)

    def _sankey_heating(self, load, load_type="heating"):
        assert load_type in ["heating", "cooling"]
        load_source = (
            load.unstack("Gain/Loss")
            .replace({0: np.NaN})
            .loc[:, "Heat Gain"]
            .dropna(how="all")
            .apply(abs)
            .rename("value")
            .reset_index()
        )
        load_target = (
            load.unstack("Gain/Loss")
            .replace({0: np.NaN})
            .loc[:, "Heat Loss"]
            .dropna(how="all")
            .apply(abs)
            .rename("value")
            .reset_index()
        )
        load_source["target"] = load_type.title() + " Load"
        load_source = load_source.rename({"Component": "source"}, axis=1)
        load_source["source"] = load_source["source"] + " Gain"
        load_source = load_source.replace(
            {f"{load_type.title()} Gain": load_type.title() + " System"}
        )

        load_source_data = load_source.to_dict(orient="records")
        load_target["source"] = load_type.title() + " Load"
        load_target = load_target.rename({"Component": "target"}, axis=1)
        load_target["target"] = load_target["target"] + " Heat Losses"
        load_target_data = load_target.to_dict(orient="records")
        link_system_to_gains = (
            load_source.set_index("source")
            .drop(load_type.title() + " System", errors="ignore")
            .rename_axis("target")
            .apply(lambda x: 0.01, axis=1)
            .rename("value")
            .reset_index()
        )
        link_system_to_gains["source"] = load_type.title()
        link_system_to_gains = link_system_to_gains.to_dict(orient="records")
        return (
            load_source_data,
            load_target_data,
            link_system_to_gains,
        )

    def _sankey_cooling(self, load, load_type="cooling"):
        assert load_type in ["heating", "cooling"]
        load_source = (
            load.unstack("Gain/Loss")
            .replace({0: np.NaN})
            .loc[:, "Heat Loss"]
            .dropna(how="all")
            .apply(abs)
            .rename("value")
            .reset_index()
        )
        load_target = (
            load.unstack("Gain/Loss")
            .replace({0: np.NaN})
            .loc[:, "Heat Gain"]
            .dropna(how="all")
            .apply(abs)
            .rename("value")
            .reset_index()
        )
        load_source["target"] = load_type.title() + " Load"
        load_source = load_source.rename({"Component": "source"}, axis=1)
        load_source["source"] = load_source["source"] + " Losses"
        load_source = load_source.replace(
            {f"{load_type.title()} Losses": load_type.title() + " System"}
        )

        load_source_data = load_source.to_dict(orient="records")
        load_target["source"] = load_type.title() + " Load"
        load_target = load_target.rename({"Component": "target"}, axis=1)
        load_target = (
            load_target.set_index("target")
            .drop(load_type.title(), errors="ignore")
            .reset_index()
        )
        load_target_data = load_target.to_dict(orient="records")
        link_system_to_gains = (
            load_source.set_index("source")
            .drop(load_type.title() + " System", errors="ignore")
            .rename_axis("target")
            .apply(lambda x: 0.01, axis=1)
            .rename("value")
            .reset_index()
        )
        link_system_to_gains["source"] = load_type.title()
        link_system_to_gains = link_system_to_gains.to_dict(orient="records")
        return (
            load_source_data,
            load_target_data,
            link_system_to_gains,
        )
