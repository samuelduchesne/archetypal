"""Window module handles window settings.

Notes:
    Thank you to `honeybee-energy <https://github.com/ladybug-tools/honeybee-energy/
    blob/master/honeybee_energy/construction/window.py>`_ for implementing center
    of glass resistance formulas from ISO. Those where adapted to the structure of the
    archetypal.template module.
"""

import collections
from enum import Enum

from validator_collection import validators

from archetypal.simple_glazing import calc_simple_glazing
from archetypal.template.constructions.base_construction import LayeredConstruction
from archetypal.template.materials.gas_layer import GasLayer
from archetypal.template.materials.gas_material import GasMaterial
from archetypal.template.materials.glazing_material import GlazingMaterial
from archetypal.template.materials.material_layer import MaterialLayer


class WindowType(Enum):
    """Refers to the window type. Two choices are available: interior or exterior."""

    External = 0
    Internal = 1

    def __lt__(self, other):
        """Return true if self lower than other."""
        return self._value_ < other._value_

    def __gt__(self, other):
        """Return true if self higher than other."""
        return self._value_ > other._value_


class ShadingType(Enum):
    """Refers to window shading types.

    Hint:
        EnergyPlus specifies 8 different shading types, but only 2 are supported
        here: InteriorShade and ExteriorShade. See shading_ for more info.

    .. _shading: https://bigladdersoftware.com/epx/docs/8-4/input-output-reference/group-thermal-zone-description-geometry.html#field-shading-type
    """

    ExteriorShade = 0
    InteriorShade = 1

    def __lt__(self, other):
        """Return true if self lower than other."""
        return self._value_ < other._value_

    def __gt__(self, other):
        """Return true if self higher than other."""
        return self._value_ > other._value_


class WindowConstruction(LayeredConstruction):
    """Window Construction.

    .. image:: ../images/template/constructions-window.png
    """

    _CATEGORIES = ("single", "double", "triple", "quadruple")

    __slots__ = ("_category",)

    def __init__(self, Name, Layers, Category="Double", **kwargs):
        """Initialize a WindowConstruction.

        Args:
            Name (str): Name of the WindowConstruction.
            Layers (list of (MaterialLayer or GasLayer)): List of MaterialLayer and
                GasLayer.
            Category (str): "Single", "Double" or "Triple".
            **kwargs: Other keywords passed to the constructor.
        """
        super(WindowConstruction, self).__init__(
            Name,
            Layers,
            Category=Category,
            **kwargs,
        )
        self.Category = Category  # set here for validators

    @property
    def Category(self):
        """Get or set the Category. Choices are ("single", "double", "triple")."""
        return self._category

    @Category.setter
    def Category(self, value):
        assert value.lower() in self._CATEGORIES, (
            f"Input error for value '{value}'. The "
            f"Category must be one of ({self._CATEGORIES})"
        )
        self._category = value

    @property
    def gap_count(self):
        """Get the number of gas gaps contained within the window construction."""
        count = 0
        for layer in self.Layers:
            if isinstance(layer, GasLayer):
                count += 1
        return count

    @property
    def glazing_count(self):
        """Get the nb of glazing materials contained within the window construction."""
        count = 0
        for layer in self.Layers:
            if isinstance(layer, MaterialLayer):
                count += 1
        return count

    @property
    def r_factor(self):
        """Get the construction R-factor [m2-K/W].

        Note: including standard resistances for air films. Formulas for film
        coefficients come from EN673 / ISO10292.
        """
        gap_count = self.gap_count
        if gap_count == 0:  # single pane
            return (
                self.Layers[0].r_value
                + (1 / self.out_h_simple())
                + (1 / self.in_h_simple())
            )
        elif gap_count == 1:
            heat_transfers, temperature_profile = self.heat_balance("summer", 0)
            *_, Q_dot_i4 = heat_transfers
            return (temperature_profile[-1] - temperature_profile[0]) / Q_dot_i4
        r_vals, emissivities = self._layered_r_value_initial(gap_count)
        r_vals = self._solve_r_values(r_vals, emissivities)
        return sum(r_vals)

    @property
    def r_value(self):
        """Get or set the thermal resistance [K⋅m2/W] (excluding air films)."""
        gap_count = self.gap_count
        if gap_count == 0:  # single pane
            return self.Layers[0].r_value
        r_vals, emissivities = self._layered_r_value_initial(gap_count)
        r_vals = self._solve_r_values(r_vals, emissivities)
        return sum(r_vals[1:-1])

    @property
    def outside_emissivity(self):
        """Get the hemispherical emissivity of the outside face of the construction."""
        return self.Layers[0].Material.IREmissivityFront

    @property
    def inside_emissivity(self):
        """Get the hemispherical emissivity of the inside face of the construction."""
        return self.Layers[-1].Material.IREmissivityBack

    @property
    def solar_transmittance(self):
        """Get the solar transmittance of the window at normal incidence."""
        if self.glazing_count == 2:
            tau_1 = self.Layers[0].Material.SolarTransmittance
            tau_2 = self.Layers[-1].Material.SolarTransmittance
            rho_1 = self.Layers[0].Material.SolarReflectanceFront
            rho_2 = self.Layers[-1].Material.SolarReflectanceFront
            return (tau_1 * tau_2) / (1 - rho_1 * rho_2)
        trans = 1
        for layer in self.Layers:
            if isinstance(layer.Material, GlazingMaterial):
                trans *= layer.Material.SolarTransmittance
        return trans

    @property
    def visible_transmittance(self):
        """Get the visible transmittance of the window at normal incidence."""
        trans = 1
        for layer in self.Layers:
            if isinstance(layer.Material, GlazingMaterial):
                trans *= layer.Material.VisibleTransmittance
        return trans

    @property
    def thickness(self):
        """Thickness of the construction [m]."""
        thickness = 0
        for layer in self.Layers:
            thickness += layer.Thickness
        return thickness

    @classmethod
    def from_dict(cls, data, materials, **kwargs):
        """Create an WindowConstruction from a dictionary.

        Args:
            data (dict): The python dictionary.
            materials (dict): A dictionary of materials with their id as keys.
            **kwargs: keywords passed to the constructor.

        .. code-block:: python

            data = {
                "$id": "57",
                "Layers": [
                    {"Material": {"$ref": "7"}, "Thickness": 0.003},
                    {"Material": {"$ref": "1"}, "Thickness": 0.006},
                    {"Material": {"$ref": "7"}, "Thickness": 0.003},
                ],
                "AssemblyCarbon": 0.0,
                "AssemblyCost": 0.0,
                "AssemblyEnergy": 0.0,
                "DisassemblyCarbon": 0.0,
                "DisassemblyEnergy": 0.0,
                "Category": "Double",
                "Comments": "default",
                "DataSource": "default",
                "Name": "B_Dbl_Air_Cl",
            }
        """
        _id = data.pop("$id")
        layers = [
            MaterialLayer(materials[layer["Material"]["$ref"]], layer["Thickness"])
            if isinstance(
                materials[layer["Material"]["$ref"]], (MaterialLayer, GlazingMaterial)
            )
            else GasLayer(materials[layer["Material"]["$ref"]], layer["Thickness"])
            for layer in data.pop("Layers")
        ]
        return cls(Layers=layers, id=_id, **data, **kwargs)

    @classmethod
    def from_epbunch(cls, Construction, **kwargs):
        """Create :class:`WindowConstruction` object from idf Construction object.

        Example:
            >>> from archetypal import IDF
            >>> from archetypal.template.window_setting import WindowSetting
            >>> idf = IDF("myidf.idf")
            >>> construction_name = "Some construction name"
            >>> WindowConstruction.from_epbunch(Name=construction_name, idf=idf)

        Args:
            Construction (EpBunch): The Construction epbunch object.
            **kwargs: Other keywords passed to the constructor.
        """
        layers = WindowConstruction._layers_from_construction(Construction, **kwargs)
        catdict = {0: "Single", 1: "Single", 2: "Double", 3: "Triple", 4: "Quadruple"}
        category = catdict[
            len([lyr for lyr in layers if isinstance(lyr.Material, GlazingMaterial)])
        ]
        return cls(Name=Construction.Name, Layers=layers, Category=category, **kwargs)

    @classmethod
    def from_shgc(
        cls,
        Name,
        solar_heat_gain_coefficient,
        u_factor,
        visible_transmittance=None,
        **kwargs,
    ):
        """Create a WindowConstruction from shgc, u_factor and visible_transmittance.

        Args:
            Name (str): The name of the window construction.
            shgc (double): The window's Solar Heat Gain Coefficient.
            u_factor (double): The window's U-value.
            visible_transmittance (double, optional): The window's visible
                transmittance. If none, the visible transmittance defaults to the
                solar transmittance t_sol.
            kwargs: keywrods passed to the parent constructor.

        Returns:

        """
        glass_properties = calc_simple_glazing(
            solar_heat_gain_coefficient,
            u_factor,
            visible_transmittance,
        )
        material_obj = GlazingMaterial(Name="Simple Glazing", **glass_properties)

        material_layer = MaterialLayer(material_obj, glass_properties["Thickness"])
        return cls(Name, Layers=[material_layer], **kwargs)

    def to_dict(self):
        """Return WindowConstruction dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Layers"] = [layer.to_dict() for layer in self.Layers]
        data_dict["AssemblyCarbon"] = self.AssemblyCarbon
        data_dict["AssemblyCost"] = self.AssemblyCost
        data_dict["AssemblyEnergy"] = self.AssemblyEnergy
        data_dict["DisassemblyCarbon"] = self.DisassemblyCarbon
        data_dict["DisassemblyEnergy"] = self.DisassemblyEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def to_epbunch(self, idf):
        """Convert self to a `Construction` epbunch given an idf model.

        Args:
            idf (IDF): The idf model in which the EpBunch is created.

        .. code-block:: python

            Construction,
                B_Dbl_Air_Cl,                           !- Name
                B_Glass_Clear_3_0.003_B_Dbl_Air_Cl,     !- Outside Layer
                AIR_0.006_B_Dbl_Air_Cl,                 !- Layer 2
                B_Glass_Clear_3_0.003_B_Dbl_Air_Cl;     !- Layer 3

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        data = {"Name": self.Name}
        for i, layer in enumerate(self.Layers):
            mat = layer.to_epbunch(idf)
            if i < 1:
                data["Outside_Layer"] = mat.Name
            else:
                data[f"Layer_{i+1}"] = mat.Name

        return idf.newidfobject("CONSTRUCTION", **data)

    def mapping(self, validate=True):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return dict(
            Layers=self.Layers,
            AssemblyCarbon=self.AssemblyCarbon,
            AssemblyCost=self.AssemblyCost,
            AssemblyEnergy=self.AssemblyEnergy,
            DisassemblyCarbon=self.DisassemblyCarbon,
            DisassemblyEnergy=self.DisassemblyEnergy,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def combine(self, other, weights=None):
        """Append other to self. Return self + other as a new object.

        For now, simply returns self.

        todo:
            - Implement equivalent window layers for constant u-factor.

        """
        # Check if other is None. Simply return self
        if not other:
            return self

        if not self:
            return other

        return self

    def validate(self):
        """Validate object and fill in missing values.

        todo:
            - Implement validation
        """
        return self

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def temperature_profile(
        self,
        outside_temperature=-18,
        inside_temperature=21,
        wind_speed=6.7,
        height=1.0,
        angle=90.0,
        pressure=101325,
    ):
        """Get a list of temperatures at each material boundary across the construction.

        Args:
            outside_temperature: The temperature on the outside of the construction [C].
                Default is -18, which is consistent with NFRC 100-2010.
            inside_temperature: The temperature on the inside of the construction [C].
                Default is 21, which is consistent with NFRC 100-2010.
            wind_speed: The average outdoor wind speed [m/s]. This affects outdoor
                convective heat transfer coefficient. Default is 6.7 m/s.
            height: An optional height for the surface in meters. Default is 1.0 m.
            angle: An angle in degrees between 0 and 180.
                0 = A horizontal surface with the outside boundary on the bottom.
                90 = A vertical surface
                180 = A horizontal surface with the outside boundary on the top.
            pressure: The average pressure of in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        Returns:
            A tuple with two elements
            -   temperatures: A list of temperature values [C].
                The first value will always be the outside temperature and the
                second will be the exterior surface temperature.
                The last value will always be the inside temperature and the second
                to last will be the interior surface temperature.
            -   r_values: A list of R-values for each of the material layers [m2-K/W].
                The first value will always be the resistance of the exterior air
                and the last value is the resistance of the interior air.
                The sum of this list is the R-factor for this construction given
                the input parameters.
        """
        # reverse the angle if the outside temperature is greater than the inside one
        if angle != 90 and outside_temperature > inside_temperature:
            angle = abs(180 - angle)
        gap_count = self.gap_count

        # single pane or simple glazing system
        if gap_count == 0:
            in_r_init = 1 / self.in_h_simple()
            r_values = [
                1 / self.out_h(wind_speed, outside_temperature + 273.15),
                self.Layers[0].r_value,
                in_r_init,
            ]
            in_delta_t = (in_r_init / sum(r_values)) * (
                outside_temperature - inside_temperature
            )
            r_values[-1] = 1 / self.in_h(
                inside_temperature - (in_delta_t / 2) + 273.15,
                in_delta_t,
                height,
                angle,
                pressure,
            )
            temperatures = self._temperature_profile_from_r_values(
                r_values, outside_temperature, inside_temperature
            )
            return temperatures, r_values

        # multi-layered window construction
        guess = abs(inside_temperature - outside_temperature) / 2
        guess = 1 if guess < 1 else guess  # prevents zero division with gas conductance
        avg_guess = ((inside_temperature + outside_temperature) / 2) + 273.15
        r_values, emissivities = self._layered_r_value_initial(
            gap_count, guess, avg_guess, wind_speed
        )
        r_last = 0
        r_next = sum(r_values)
        while abs(r_next - r_last) > 0.001:  # 0.001 is the r-value tolerance
            r_last = sum(r_values)
            temperatures = self._temperature_profile_from_r_values(
                r_values, outside_temperature, inside_temperature
            )
            r_values = self._layered_r_value(
                temperatures, r_values, emissivities, height, angle, pressure
            )
            r_next = sum(r_values)
        temperatures = self._temperature_profile_from_r_values(
            r_values, outside_temperature, inside_temperature
        )
        return temperatures, r_values

    @staticmethod
    def _layers_from_construction(construction, **kwargs):
        """Retrieve layers for the Construction epbunch."""
        layers = []
        for field in construction.fieldnames[2:]:
            # Loop through the layers from the outside layer towards the
            # indoor layers and get the material they are made of.
            material = construction.get_referenced_object(field) or kwargs.get(
                "material", None
            )
            if material:
                # Create the WindowMaterial:Glazing or the WindowMaterial:Gas
                # and append to the list of layers
                if material.key.upper() == "WindowMaterial:Glazing".upper():
                    material_obj = GlazingMaterial(
                        Name=material.Name,
                        Conductivity=material.Conductivity,
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
                        Optical=material.Optical_Data_Type,
                        OpticalData=material.Window_Glass_Spectral_Data_Set_Name,
                    )

                    material_layer = MaterialLayer(material_obj, material.Thickness)

                elif material.key.upper() == "WindowMaterial:Gas".upper():
                    # Todo: Make gas name generic, like in UmiTemplateLibrary Editor
                    material_obj = GasMaterial(
                        Name=material.Gas_Type.upper(), Conductivity=0.02
                    )
                    material_layer = GasLayer(material_obj, material.Thickness)
                elif material.key.upper() == "WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM":
                    glass_properties = calc_simple_glazing(
                        material.Solar_Heat_Gain_Coefficient,
                        material.UFactor,
                        material.Visible_Transmittance,
                    )
                    material_obj = GlazingMaterial(
                        Name=material.Name, **glass_properties
                    )

                    material_layer = MaterialLayer(
                        material_obj, glass_properties["Thickness"]
                    )
                    layers.append(material_layer)
                    break
                else:
                    continue

                layers.append(material_layer)
        return layers

    def _layered_r_value_initial(
        self, gap_count, delta_t_guess=15, avg_t_guess=273.15, wind_speed=6.7
    ):
        """Compute initial r-values of each layer within a layered construction."""
        r_vals = [1 / self.out_h(wind_speed, avg_t_guess - delta_t_guess)]
        emiss = []
        delta_t = delta_t_guess / gap_count
        for i, lyr in enumerate(self.Layers):
            if isinstance(lyr, MaterialLayer):
                r_vals.append(lyr.r_value)
                emiss.append(None)
            else:  # gas layer
                e_front = self.Layers[i + 1].Material.IREmissivityFront
                e_back = self.Layers[i + 1].Material.IREmissivityBack
                r_vals.append(
                    1 / lyr.u_value(delta_t, e_back, e_front, t_kelvin=avg_t_guess)
                )
                emiss.append((e_back, e_front))
        r_vals.append(1 / self.in_h_simple())
        return r_vals, emiss

    def __hash__(self):
        """Return the hash value of self."""
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, WindowConstruction):
            return NotImplemented
        else:
            return all(
                [
                    self.Category == other.Category,
                    self.AssemblyCarbon == other.AssemblyCarbon,
                    self.AssemblyCost == other.AssemblyCost,
                    self.AssemblyEnergy == other.AssemblyEnergy,
                    self.DisassemblyCarbon == other.DisassemblyCarbon,
                    self.DisassemblyEnergy == other.DisassemblyEnergy,
                    self.Layers == other.Layers,
                ]
            )

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(**self.mapping())

    def __add__(self, other):
        """Combine self and other."""
        return self.combine(other)

    def _solve_r_values(self, r_values, emissivities):
        """Solve iteratively for R-values."""
        r_last = 0
        r_next = sum(r_values)
        while abs(r_next - r_last) > 0.001:  # 0.001 is the r-value tolerance
            r_last = sum(r_values)
            temperatures = self._temperature_profile_from_r_values(r_values)
            r_values = self._layered_r_value(temperatures, r_values, emissivities)
            r_next = sum(r_values)
        return r_values

    def _temperature_profile_from_r_values(
        self, r_values, outside_temperature=-18, inside_temperature=21
    ):
        """Get a list of temperatures at each material boundary between R-values."""
        r_factor = sum(r_values)
        delta_t = inside_temperature - outside_temperature
        temperatures = [outside_temperature]
        for i, r_val in enumerate(r_values):
            temperatures.append(temperatures[i] + (delta_t * (r_val / r_factor)))
        return temperatures

    def _layered_r_value(
        self,
        temperatures,
        r_values_init,
        emiss,
        height=1.0,
        angle=90.0,
        pressure=101325,
    ):
        """Compute delta_t adjusted r-values of each layer within a construction."""
        r_vals = [r_values_init[0]]
        for i, layer in enumerate(self.Layers):
            if isinstance(layer, MaterialLayer):
                r_vals.append(r_values_init[i + 1])
            elif isinstance(layer, GasLayer):  # gas layer
                delta_t = abs(temperatures[i + 1] - temperatures[i + 2])
                avg_temp = ((temperatures[i + 1] + temperatures[i + 2]) / 2) + 273.15
                r_vals.append(
                    1
                    / layer.u_value_at_angle(
                        delta_t,
                        emiss[i][0],
                        emiss[i][1],
                        height,
                        angle,
                        avg_temp,
                        pressure,
                    )
                )
        delta_t = abs(temperatures[-1] - temperatures[-2])
        avg_temp = ((temperatures[-1] + temperatures[-2]) / 2) + 273.15
        r_vals.append(1 / self.in_h(avg_temp, delta_t, height, angle, pressure))
        return r_vals

    def shgc(self, environmental_conditions="summer", global_radiation=783):
        """Calculate the shgc given environmental conditions.

        Notes:
            This method implements a heat balance at each interface of the
            glazing unit including outside and inside air film resistances,
            solar radiation absorption in the glass. See
            :meth:`~archetypal.template.constructions.window_construction
            .WindowConstruction.heat_balance` for more details.

        Args:
            environmental_conditions (str): "summer" or "winter". A window shgc is
                usually calculated with summer conditions. Default is "summer".
            global_radiation (float): Incident solar radiation [W / m ^ 2]. Overwrite
                the solar radiation used in the calculation of the shgc.

        Returns:
            float: The shgc of the window construction for the given environmental
            conditions.
        """
        # Q_dot_noSun
        heat_transfers, temperature_profile = self.heat_balance(
            environmental_conditions, 0
        )
        *_, Q_dot_noSun = heat_transfers

        # Q_dot_Sun
        heat_transfers, temperature_profile = self.heat_balance(
            environmental_conditions, 783
        )
        *_, Q_dot_i4 = heat_transfers

        Q_dot_sun = -Q_dot_i4 + self.solar_transmittance * global_radiation
        shgc = (Q_dot_sun - -Q_dot_noSun) / global_radiation
        return shgc

    def heat_balance(self, environmental_conditions="summer", G_t=783):
        """Return heat flux and temperatures at each surface of the window.

        Note: Only implemented for glazing with two layers.

        Args:
            environmental_conditions (str): The environmental conditions from
                the NRFC standard used to calculate the heat balance. Default is
                "summer".
            G_t (float): The incident radiation.

        Returns:
            tuple: heat_flux, temperature_profile
        """
        assert (
            self.glazing_count == 2
        ), f"Expected a window with 2 glazing layers, not {self.glazing_count}."
        ENV_CONDITIONS = {"summer": [32, 24, 2.75], "winter": [-18, 21, 5.5]}
        (
            outside_temperature,
            inside_temperature,
            environmental_conditions,
        ) = ENV_CONDITIONS[environmental_conditions]
        temperatures_next, r_values = self.temperature_profile(
            outside_temperature, inside_temperature, environmental_conditions
        )
        temperatures_last = [0] * 6
        pressure = 101325  # [Pa]
        height = 1  # [m]
        angle = 90  # degree
        k_g = 1  # [W / m - K]
        sigma = 5.670e-8  # [W / m2 - K4]
        # "21011 (SGG Planiclear 4 mm), Air 12 mm, 21414 (SGG Planitherm One 4 mm)"
        epsilon_1 = self.Layers[0].Material.IREmissivityFront  # [-]
        epsilon_2 = self.Layers[0].Material.IREmissivityBack  # [-]
        epsilon_3 = self.Layers[-1].Material.IREmissivityFront  # [-]
        epsilon_4 = self.Layers[-1].Material.IREmissivityBack  # [-]
        abs_1 = 0.0260  # [-]
        abs_2 = 0.0737  # [-]
        L_12 = self.Layers[0].Thickness  # [m]
        L_23 = self.Layers[1].Thickness  # [m]  # included in Layers[1] used below
        L_34 = self.Layers[2].Thickness  # [m]
        # "Solar absorption distribution"
        Q_dot_abs_1 = abs_1 / self.glazing_count * G_t
        Q_dot_abs_2 = abs_1 / self.glazing_count * G_t
        Q_dot_abs_3 = abs_2 / self.glazing_count * G_t
        Q_dot_abs_4 = abs_2 / self.glazing_count * G_t
        T_o, T_1, T_2, T_3, T_4, T_i = temperatures_next
        while not self.assert_almost_equal(temperatures_last, temperatures_next):
            temperatures_last = [T_o, T_1, T_2, T_3, T_4, T_i]

            # "Heat balance at surface 1"
            h_c_o = 4 + 4 * environmental_conditions
            Q_dot_c_1o = h_c_o * (T_1 - T_o)
            Q_dot_r_1o = epsilon_1 * sigma * ((T_1 + 273.15) ** 4 - (T_o + 273.15) ** 4)
            Q_dot_1o = Q_dot_c_1o + Q_dot_r_1o
            Q_dot_21 = k_g / L_12 * (T_2 - T_1)  # + Q_dot_abs_1

            # "Heat balance at surface 2"
            h_c_32 = self.Layers[1].convective_conductance_at_angle(
                abs(T_3 - T_2), height, angle, (T_3 + T_2) / 2 + 273.15, pressure
            )
            Q_dot_c_32 = h_c_32 * (T_3 - T_2)
            Q_dot_r_32 = (
                sigma
                * ((T_3 + 273.15) ** 4 - (T_2 + 273.15) ** 4)
                / (1 / epsilon_2 + 1 / epsilon_3 - 1)
            )
            Q_dot_32 = Q_dot_c_32 + Q_dot_r_32

            # "Heat balance at surface 3"
            Q_dot_43 = k_g / L_34 * (T_4 - T_3)  # + Q_dot_abs_3

            # Q_dot_32 = Q_dot_abs_3 + Q_dot_43

            # "Heat balance at surface 4"
            h_c_i = self.in_h_c(
                (T_4 + T_i) / 2 + 273.15, abs(T_i - T_4), height, angle, pressure
            )
            Q_dot_c_i4 = h_c_i * (T_i - T_4)
            Q_dot_r_i4 = epsilon_4 * sigma * ((T_i + 273.15) ** 4 - (T_4 + 273.15) ** 4)
            Q_dot_i4 = Q_dot_c_i4 + Q_dot_r_i4

            # calc new temps
            T_1 = T_2 - (Q_dot_1o - Q_dot_abs_1) / k_g * L_12
            T_2 = (Q_dot_abs_2 + Q_dot_32) / k_g * L_12 + T_1
            T_3 = T_4 - (Q_dot_32 - Q_dot_abs_3) / k_g * L_34
            T_4 = (Q_dot_abs_4 + Q_dot_i4) / k_g * L_34 + T_3

            temperatures_next = [T_o, T_1, T_2, T_3, T_4, T_i]
        heat_transfers = [Q_dot_1o, Q_dot_21, Q_dot_32, Q_dot_43, Q_dot_i4]
        return heat_transfers, temperatures_next

    def assert_almost_equal(self, temperatures_last, temperatures_next):
        return all(
            abs(desired - actual) < 1.5 * 10 ** (-3)
            for desired, actual in zip(temperatures_last, temperatures_next)
        )
