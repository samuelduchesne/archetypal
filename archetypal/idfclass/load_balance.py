import pandas as pd
from energy_pandas import EnergyDataFrame


class LoadBalance:
    def __init__(
        self,
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
        units="J",
        use_all_solar=True,
    ):
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
        self.units = units
        self.use_all_solar = use_all_solar

    @classmethod
    def from_idf(cls, idf):
        assert idf.sql_file.exists()

        # get all of the results relevant for gains and losses
        cooling = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.COOLING, reporting_frequency=idf.outputs.reporting_frequency
        )
        heating = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.HEATING, reporting_frequency=idf.outputs.reporting_frequency
        )
        lighting = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.LIGHTING, reporting_frequency=idf.outputs.reporting_frequency
        )
        people_gain = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.PEOPLE_GAIN, reporting_frequency=idf.outputs.reporting_frequency
        )
        solar_gain = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.SOLAR_GAIN, reporting_frequency=idf.outputs.reporting_frequency
        )
        infil_gain = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.INFIL_GAIN, reporting_frequency=idf.outputs.reporting_frequency
        )
        infil_loss = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.INFIL_LOSS, reporting_frequency=idf.outputs.reporting_frequency
        )
        vent_loss = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.VENT_LOSS, reporting_frequency=idf.outputs.reporting_frequency
        )
        vent_gain = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.VENT_GAIN, reporting_frequency=idf.outputs.reporting_frequency
        )
        nat_vent_gain = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.NAT_VENT_GAIN,
            reporting_frequency=idf.outputs.reporting_frequency,
        )
        nat_vent_loss = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.NAT_VENT_LOSS,
            reporting_frequency=idf.outputs.reporting_frequency,
        )

        # handle the case that both total elect/gas energy and zone gain are requested
        electric_equip = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.ELECTRIC_EQUIP[1],
            reporting_frequency=idf.outputs.reporting_frequency,
        )
        if len(electric_equip) == 0:
            electric_equip = idf.variables.OutputVariable.collect_by_output_name(
                idf.outputs.ELECTRIC_EQUIP,
                reporting_frequency=idf.outputs.reporting_frequency,
            )
        gas_equip = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.GAS_EQUIP[1],
            reporting_frequency=idf.outputs.reporting_frequency,
        )
        if len(gas_equip) == 0:
            gas_equip = idf.variables.OutputVariable.collect_by_output_name(
                idf.outputs.GAS_EQUIP,
                reporting_frequency=idf.outputs.reporting_frequency,
            )
        hot_water = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.HOT_WATER[1],
            reporting_frequency=idf.outputs.reporting_frequency,
        )
        if len(hot_water) == 0:
            hot_water = idf.variables.OutputVariable.collect_by_output_name(
                idf.outputs.HOT_WATER,
                reporting_frequency=idf.outputs.reporting_frequency,
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
            idf.outputs.OPAQUE_ENERGY_FLOW,
            reporting_frequency=idf.outputs.reporting_frequency,
        )
        window_loss = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.WINDOW_LOSS, reporting_frequency=idf.outputs.reporting_frequency
        )
        window_gain = idf.variables.OutputVariable.collect_by_output_name(
            idf.outputs.WINDOW_GAIN, reporting_frequency=idf.outputs.reporting_frequency
        )
        window_flow = []
        if window_gain.shape == window_loss.shape:
            window_flow = cls.subtract_loss_from_gain(window_gain, window_loss)
            window_flow = cls.match_window_to_zone(idf, window_flow)
        face_energy_flow = opaque_flow.add(
            window_flow.sum(level=["Building_Surface_Name"], axis=1).rename(
                columns=str.upper
            ),
            level="Key_Name",
            axis=1,
            fill_value=0,
        )

        bal_obj = cls(
            cooling,
            heating,
            lighting,
            electric_equip,
            gas_equip,
            hot_water,
            people_gain,
            solar_gain,
            infiltration,
            mech_vent,
            nat_vent,
            face_energy_flow,
            "J",
            use_all_solar=True,
        )
        return bal_obj

    @classmethod
    def match_window_to_zone(cls, idf, window_flow):
        """Match the DataFrame of"""
        assert window_flow.columns.names == ["OutputVariable", "Key_Name"]
        window_to_surface_match = pd.DataFrame(
            [
                (
                    window.Name,  # name of the window
                    window.Building_Surface_Name,  # name of the wall this window is on
                    window.get_referenced_object(
                        "Building_Surface_Name"
                    ).Surface_Type,  # surface type (wall, ceiling, floor) this windows is on.
                    window.get_referenced_object(  # get the zone name though the surface name
                        "Building_Surface_Name"
                    ).Zone_Name,
                    window.Multiplier,  # multiplier of this window.
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
        window_flow = stacked.drop(columns=["Multiplier"]).iloc[:, 0] * pd.to_numeric(
            stacked["Multiplier"]
        )
        window_flow = window_flow.unstack(
            level=["Key_Name", "Building_Surface_Name", "Surface_Type", "Zone_Name"]
        )

        return window_flow  # .groupby("Building_Surface_Name", axis=1).sum()

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

    def to_df(self):
        return pd.concat(
            [
                df
                for df in [
                    self.cooling,
                    self.heating,
                    self.lighting,
                    self.electric_equip,
                    self.gas_equip,
                    self.hot_water,
                    self.people_gain,
                    self.solar_gain,
                    self.infiltration,
                    self.mech_vent,
                    self.nat_vent,
                    self.face_energy_flow,
                ]
                if not df.empty
            ],
            axis=1,
            verify_integrity=True,
        )
