import numpy as np
import pandas as pd
from energy_pandas import EnergyDataFrame
from energy_pandas.units import unit_registry


class EndUseBalance:
    HVAC_INPUT_SENSIBLE = (
        "Zone Air Heat Balance System Air Transfer Rate",
        "Zone Air Heat Balance System Convective Heat Gain Rate",
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
    PEOPLE_GAIN = ("Zone People Sensible Heating Energy",)  # checked
    SOLAR_GAIN = ("Zone Windows Total Transmitted Solar Radiation Energy",)  # checked
    INFIL_GAIN = (
        "Zone Infiltration Sensible Heat Gain Energy",  # checked
        "Zone Infiltration Latent Heat Gain Energy",
        "AFN Zone Infiltration Sensible Heat Gain Energy",
        "AFN Zone Infiltration Latent Heat Gain Energy",
    )
    INFIL_LOSS = (
        "Zone Infiltration Sensible Heat Loss Energy",  # checked
        "Zone Infiltration Latent Heat Loss Energy",
        "AFN Zone Infiltration Sensible Heat Loss Energy",
        "AFN Zone Infiltration Latent Heat Loss Energy",
    )
    VENTILATION_LOSS = ("Air System Total Heating Energy",)
    VENTILATION_GAIN = ("Air System Total Cooling Energy",)
    NAT_VENT_GAIN = (
        "Zone Ventilation Total Heat Gain Energy",
        "Zone Ventilation Sensible Heat Gain Energy",
        "Zone Ventilation Latent Heat Gain Energy",
        "AFN Zone Ventilation Sensible Heat Gain Energy",
        "AFN Zone Ventilation Latent Heat Gain Energy",
    )
    NAT_VENT_LOSS = (
        "Zone Ventilation Total Heat Loss Energy",
        "Zone Ventilation Sensible Heat Loss Energy",
        "Zone Ventilation Latent Heat Loss Energy",
        "AFN Zone Ventilation Sensible Heat Loss Energy",
        "AFN Zone Ventilation Latent Heat Loss Energy",
    )
    OPAQUE_ENERGY_FLOW = ("Surface Average Face Conduction Heat Transfer Energy",)
    WINDOW_LOSS = ("Surface Window Heat Loss Energy",)  # checked
    WINDOW_GAIN = ("Surface Window Heat Gain Energy",)  # checked

    def __init__(
        self,
        idf,
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
        face_energy_flow,
        window_energy_flow,
        opaque_flow,
        window_flow,
        is_cooling,
        is_heating,
        units="J",
        use_all_solar=True,
    ):
        self.idf = idf
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
        self.face_energy_flow = face_energy_flow
        self.window_energy_flow = window_energy_flow
        self.opaque_flow = opaque_flow
        self.window_flow = window_flow
        self.units = units
        self.use_all_solar = use_all_solar
        self.is_cooling = is_cooling
        self.is_heating = is_heating

    @classmethod
    def from_idf(
        cls,
        idf,
        units="kWh",
        power_units="kW",
        outdoor_surfaces_only=True,
        temperature_units="degC",
    ):
        assert (
            idf.sql_file.exists()
        ), "Expected an IDF model with simulation results. Run `IDF.simulate()` first."
        # get all of the results relevant for gains and losses
        _hvac_input = idf.variables.OutputVariable.collect_by_output_name(
            cls.HVAC_INPUT_SENSIBLE,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=power_units,
        )
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

        rolling_sign = cls.get_rolling_sign_change(_hvac_input)

        # Create both heating and cooling masks
        is_heating = rolling_sign > 0
        is_cooling = rolling_sign < 0

        heating = _hvac_input[is_heating].fillna(0)
        cooling = _hvac_input[is_cooling].fillna(0)
        lighting = idf.variables.OutputVariable.collect_by_output_name(
            cls.LIGHTING,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        people_gain = idf.variables.OutputVariable.collect_by_output_name(
            cls.PEOPLE_GAIN,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        solar_gain = idf.variables.OutputVariable.collect_by_output_name(
            cls.SOLAR_GAIN,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        infil_gain = idf.variables.OutputVariable.collect_by_output_name(
            cls.INFIL_GAIN,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        infil_loss = idf.variables.OutputVariable.collect_by_output_name(
            cls.INFIL_LOSS,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        vent_loss = idf.variables.OutputVariable.collect_by_output_name(
            cls.VENTILATION_LOSS,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        vent_gain = idf.variables.OutputVariable.collect_by_output_name(
            cls.VENTILATION_GAIN,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        nat_vent_gain = idf.variables.OutputVariable.collect_by_output_name(
            cls.NAT_VENT_GAIN,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        nat_vent_loss = idf.variables.OutputVariable.collect_by_output_name(
            cls.NAT_VENT_LOSS,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )

        # handle the case that both total elect/gas energy and zone gain are requested
        equipment = idf.variables.OutputVariable.collect_by_output_name(
            cls.EQUIP_GAINS,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )

        # subtract losses from gains
        infiltration = None
        mech_vent = None
        nat_vent = None
        if len(infil_gain) == len(infil_loss):
            infiltration = cls.subtract_loss_from_gain(infil_gain, infil_loss)
        if (
            vent_gain.shape == vent_loss.shape == cooling.shape == heating.shape
            and not vent_gain.empty == vent_loss.empty == cooling.empty == heating.empty
        ):
            mech_vent_loss = cls.subtract_loss_from_gain(heating, vent_loss)
            mech_vent_gain = cls.subtract_loss_from_gain(cooling, vent_gain)
            total_load = cls.subtract_loss_from_gain(mech_vent_gain, mech_vent_loss)
            mech_vent = total_load.copy()
            mech_vent.rename(
                columns=lambda x: str.replace(
                    x, "Zone Ideal Loads Supply Air", "Zone Ideal Loads Ventilation"
                ),
                level="OutputVariable",
                inplace=True,
            )
        if nat_vent_gain.shape == nat_vent_loss.shape:
            nat_vent = cls.subtract_loss_from_gain(nat_vent_gain, nat_vent_loss)

        # get the surface energy flow
        opaque_flow = idf.variables.OutputVariable.collect_by_output_name(
            cls.OPAQUE_ENERGY_FLOW,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        window_loss = idf.variables.OutputVariable.collect_by_output_name(
            cls.WINDOW_LOSS,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        window_gain = idf.variables.OutputVariable.collect_by_output_name(
            cls.WINDOW_GAIN,
            reporting_frequency=idf.outputs.reporting_frequency,
            units=units,
        )
        window_flow = []
        if window_gain.shape == window_loss.shape:
            window_flow = cls.subtract_loss_from_gain(window_gain, window_loss)
            window_flow = cls.match_window_to_zone(idf, window_flow)

            # todo: calculate when in cooling
            # Todo: create tables with breakdown when in cooling and not of opaque_flow, window_flow, lighting, equipment
            # Zone_Windows_Total_Heat_Gain_Energy = (
            #     idf.variables.OutputVariable.Zone_Windows_Total_Heat_Gain_Energy.values()
            # )
            # Zone_Windows_Total_Heat_Loss_Energy = (
            #     idf.variables.OutputVariable.Zone_Windows_Total_Heat_Loss_Energy.values()
            # )
            # Zone_Windows_Total_Heat_Energy = (
            #     Zone_Windows_Total_Heat_Gain_Energy
            #     - Zone_Windows_Total_Heat_Loss_Energy
            # )
            # solar_gains = (
            #     idf.variables.OutputVariable.Zone_Windows_Total_Transmitted_Solar_Radiation_Energy.values()
            # )
            # # redefine is_cooling
            # is_cooling = _hvac_input.sum(level="Key_Name", axis=1) < 0
            # is_heating = _hvac_input.sum(level="Key_Name", axis=1) >= 0
            # (Zone_Windows_Total_Heat_Energy - solar_gains)[~is_cooling][
            #     lambda x: x < 0
            # ].sum().sum()
            # (Zone_Windows_Total_Heat_Energy - solar_gains)[~is_cooling][
            #     lambda x: x >= 0
            # ].sum().sum()
            # (Zone_Windows_Total_Heat_Energy - solar_gains)[is_cooling][
            #     lambda x: x < 0
            # ].sum().sum()
            # (Zone_Windows_Total_Heat_Energy - solar_gains)[is_cooling][
            #     lambda x: x >= 0
            # ].sum().sum()

            # # solar_gains[~is_cooling][lambda x: x < 0].sum().sum()
            # solar_gains[~is_cooling][
            #     lambda x: x >= 0
            # ].sum().sum()  # solar gains when heating occurs (passive solar gains)
            # # solar_gains[is_cooling][lambda x: x < 0].sum().sum()
            # solar_gains[is_cooling][
            #     lambda x: x >= 0
            # ].sum().sum()  # solar gains when cooling occurs (solar component)

        opaque_flow = cls.match_opaque_surface_to_zone(idf, opaque_flow)
        if outdoor_surfaces_only:
            opaque_flow = opaque_flow.drop(
                ["Surface", float("nan")], level="Outside_Boundary_Condition", axis=1
            )
        face_energy_flow = opaque_flow
        window_energy_flow = window_flow

        bal_obj = cls(
            idf,
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
            face_energy_flow,
            window_energy_flow,
            opaque_flow,
            window_flow,
            is_cooling,
            is_heating,
            units,
            use_all_solar=True,
        )
        return bal_obj

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
        # From sign, keep when a the sign switches and fill with the previous values
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
                    float(window.Multiplier) or 1,  # multiplier of this window.
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
    def match_opaque_surface_to_zone(cls, idf, opaque_flow):
        """Match opaque surfaces with their zone.

        Multiplies the surface heat flow by the zone multiplier.

        Adds the following properties to the `opaque_flow` DataFrame as a MultiIndex level with names:
            * Surface_Type
            * Outside_Boundary_Condition
            * Zone_Name
        """
        assert opaque_flow.columns.names == ["OutputVariable", "Key_Name"]
        wall_to_surface_match = pd.DataFrame(
            [
                (
                    surface.Name.upper(),  # name of the surface
                    surface.Surface_Type.title(),  # surface type (wall, ceiling, floor) this windows is on.
                    surface.Outside_Boundary_Condition.title(),  # the boundary of the surface.
                    surface.Zone_Name.upper(),
                    float(surface.get_referenced_object("Zone_Name").Multiplier)
                    or 1,  # multiplier of the zone.
                )
                for surface in idf.getsurfaces()
            ],
            columns=[
                "Name",
                "Surface_Type",
                "Outside_Boundary_Condition",
                "Zone_Name",
                "Multiplier",
            ],
        ).set_index("Name")
        # Match the subsurface to the surface name and the zone name it belongs to.
        stacked = (
            opaque_flow.stack()
            .join(
                wall_to_surface_match.rename(index=str.upper),
                on="Key_Name",
            )
            .set_index(
                ["Surface_Type", "Outside_Boundary_Condition", "Zone_Name"], append=True
            )
        )
        opaque_flow = (
            stacked.drop(columns=["Multiplier"]).iloc[:, 0] * stacked["Multiplier"]
        )
        opaque_flow = opaque_flow.unstack(
            level=[
                "Key_Name",
                "Surface_Type",
                "Outside_Boundary_Condition",
                "Zone_Name",
            ]
        )

        return opaque_flow  # .groupby("Building_Surface_Name", axis=1).sum()

    @classmethod
    def subtract_loss_from_gain(cls, load_gain, load_loss):
        try:
            columns = load_gain.rename(
                columns=lambda x: str.replace(x, " Gain", ""), level="OutputVariable"
            ).columns
        except KeyError:
            columns = None
        return EnergyDataFrame(
            load_gain.values - load_loss.values,
            columns=columns,
            index=load_gain.index,
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
        if isinstance(level, str):
            level = [level]

        # mask when cooling occurs in zone (negative values)
        mask = (self.is_cooling.stack("Key_Name") == True).any(axis=1)

        # get the dataframe using the attribute name, summarize by `level` and stack so that a Series is returned.
        stacked = getattr(self, component).sum(level=level, axis=1).stack(level[0])

        # concatenate the masked values with keys to easily create a MultiIndex when unstacking
        inter = pd.concat(
            [
                stacked[mask].reindex(stacked.index),
                stacked[~mask].reindex(stacked.index),
            ],
            keys=["Cooling Periods", "Heating Periods"],
            names=["Period"]
            + stacked.index.names,  # prepend the new key name to the existing index names.
        )

        # mask when values are positive (gain)
        positive_mask = inter >= 0

        # concatenate the masked values with keys to easily create a MultiIndex when unstacking
        final = pd.concat(
            [
                inter[positive_mask].reindex(inter.index),
                inter[~positive_mask].reindex(inter.index),
            ],
            keys=["Heat Gain", "Heat Loss"],
            names=["Gain/Loss"] + inter.index.names,
        ).unstack(["Period", "Gain/Loss"])
        final.sort_index(axis=1, inplace=True)
        return final

    def to_df(self, separate_gains_and_losses=False):
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
            ]:
                if not getattr(self, component).empty:
                    summary_by_component[component] = (
                        self.separate_gains_and_losses(
                            component,
                            level="Key_Name",
                        )
                        .unstack("Key_Name")
                        .reorder_levels(["Key_Name", "Period", "Gain/Loss"], axis=1)
                        .sort_index(axis=1)
                    )
            for (zone_name, surface_type), data in (
                self.separate_gains_and_losses(
                    "face_energy_flow", ["Zone_Name", "Surface_Type"]
                )
                .unstack("Zone_Name")
                .groupby(level=["Zone_Name", "Surface_Type"], axis=1)
            ):
                summary_by_component[surface_type] = data.sum(
                    level=["Zone_Name", "Period", "Gain/Loss"], axis=1
                ).sort_index(axis=1)

            for (zone_name, surface_type), data in (
                self.separate_gains_and_losses(
                    "window_energy_flow", ["Zone_Name", "Surface_Type"]
                )
                .unstack("Zone_Name")
                .groupby(level=["Zone_Name", "Surface_Type"], axis=1)
            ):
                summary_by_component[f"Window..{surface_type}"] = data.sum(
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
            ]:
                component_df = getattr(self, component)
                if not component_df.empty:
                    summary_by_component[component] = component_df.sum(
                        level="Key_Name", axis=1
                    ).sort_index(axis=1)
            for (zone_name, surface_type), data in self.face_energy_flow.groupby(
                level=["Zone_Name", "Surface_Type"], axis=1
            ):
                summary_by_component[surface_type] = data.sum(
                    level="Zone_Name", axis=1
                ).sort_index(axis=1)
            levels = ["Component", "Zone_Name"]
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

    def to_sankey(self):
        system_data = self.to_df(separate_gains_and_losses=True)
        annual_system_data = system_data.sum().sum(
            level=["Component", "Period", "Gain/Loss"]
        )

        heating_load = annual_system_data.xs("Heating Periods", level="Period")
        cooling_load = annual_system_data.xs("Cooling Periods", level="Period")

        system_input = self.idf.htm()["End Uses"].set_index("").head(-2).astype(float)
        system_input = (
            system_input.replace({0: np.NaN})
            .dropna(how="all")
            .dropna(how="all", axis=1)
        )
        system_input.rename_axis("source", axis=1, inplace=True)
        system_input.rename_axis("target", axis=0, inplace=True)
        system_input = (
            system_input.unstack()
            .rename("value")
            .reset_index()
            .dropna()
            .to_dict(orient="records")
        )

        (
            heating_energy_to_heating_system,
            heating_load_source_data,
            heating_load_target_data,
            link_heating_system_to_gains,
        ) = self._sankey_heating(heating_load, load_type="heating")

        (
            cooling_energy_to_heating_system,
            cooling_load_source_data,
            cooling_load_target_data,
            link_cooling_system_to_gains,
        ) = self._sankey_cooling(cooling_load, load_type="cooling")

        return pd.DataFrame(
            system_input
            + link_heating_system_to_gains
            + heating_energy_to_heating_system
            + heating_load_source_data
            + heating_load_target_data
            + cooling_energy_to_heating_system
            + cooling_load_source_data
            + cooling_load_target_data
            + link_cooling_system_to_gains
        ).to_csv("sankey_data.csv", index=False)

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
        load_source = load_source.replace({f"{load_type} Gain": load_type})

        load_source_data = load_source.to_dict(orient="records")
        load_target["source"] = load_type.title() + " Load"
        load_target = load_target.rename({"Component": "target"}, axis=1)
        load_target_data = load_target.to_dict(orient="records")
        energy_to_hvac_system = [
            {
                "source": load_type.title(),
                "target": load_type.title() + " System",
                "value": load_source.set_index("source").at[load_type, "value"],
            }
        ]
        link_system_to_gains = (
            load_source.set_index("source")
            .drop(load_type)
            .rename_axis("target")
            .apply(lambda x: 0.01, axis=1)
            .rename("value")
            .reset_index()
        )
        link_system_to_gains["source"] = load_type.title()
        link_system_to_gains = link_system_to_gains.to_dict(orient="records")
        return (
            energy_to_hvac_system,
            load_source_data,
            load_target_data,
            link_system_to_gains,
        )

    def _sankey_cooling(self, load, load_type="cooling"):
        load_source = (
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
        load_source["source"] = load_source["source"] + " Loss"
        load_source = load_source.replace({f"{load_type} Loss": load_type})
        load_source_data = load_source.to_dict(orient="records")

        load_target = (
            load.unstack("Gain/Loss")
            .replace({0: np.NaN})
            .loc[:, "Heat Gain"]
            .dropna(how="all")
            .apply(abs)
            .rename("value")
            .reset_index()
        )
        load_target["source"] = load_type.title() + " Load"
        load_target = load_target.rename({"Component": "target"}, axis=1)
        load_target_data = load_target.to_dict(orient="records")
        energy_to_hvac_system = [
            {
                "source": load_type.title(),
                "target": load_type.title() + " System",
                "value": load_source.set_index("source").at[load_type, "value"],
            }
        ]
        link_system_to_gains = (
            load_source.set_index("source")
            .drop(load_type)
            .rename_axis("target")
            .apply(lambda x: 0.01, axis=1)
            .rename("value")
            .reset_index()
        )
        link_system_to_gains["source"] = load_type.title()
        link_system_to_gains = link_system_to_gains.to_dict(orient="records")
        return (
            energy_to_hvac_system,
            load_source_data,
            load_target_data,
            link_system_to_gains,
        )
