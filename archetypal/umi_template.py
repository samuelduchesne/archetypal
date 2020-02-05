import io
import json
import os
from collections import OrderedDict

import numpy as np
from path import Path

from archetypal import (
    load_idf,
    BuildingTemplate,
    GasMaterial,
    GlazingMaterial,
    OpaqueMaterial,
    OpaqueConstruction,
    WindowConstruction,
    StructureDefinition,
    DaySchedule,
    WeekSchedule,
    YearSchedule,
    DomesticHotWaterSetting,
    VentilationSetting,
    ZoneConditioning,
    ZoneConstructionSet,
    ZoneLoad,
    Zone,
    settings,
    UmiBase,
    MaterialLayer,
    YearScheduleParts,
    UmiSchedule,
    MassRatio,
)


class UmiTemplate:
    """Main class supporting the definition of a multiple building templates and
    corresponding template objects.
    """
    def __init__(
        self,
        name="unnamed",
        BuildingTemplates=None,
        GasMaterials=None,
        GlazingMaterials=None,
        OpaqueConstructions=None,
        OpaqueMaterials=None,
        WindowConstructions=None,
        StructureDefinitions=None,
        DaySchedules=None,
        WeekSchedules=None,
        YearSchedules=None,
        DomesticHotWaterSettings=None,
        VentilationSettings=None,
        WindowSettings=None,
        ZoneConditionings=None,
        ZoneConstructionSets=None,
        ZoneLoads=None,
        Zones=None,
    ):
        """Initialize a new UmiTemplate with empty attributes.

        Args:
            name (str): The name of the UMI Template.
            BuildingTemplates (list of BuildingTemplate): list of
                BuildingTemplate objects.
            GasMaterials (list of GasMaterial): list of GasMaterial objects.
            GlazingMaterials (list of GlazingMaterial): list of GlazingMaterial
                objects.
            OpaqueConstructions (list of OpaqueConstruction): list of
                OpaqueConstruction objects.
            OpaqueMaterials (list of OpaqueMaterial): list of OpaqueMaterial
                objects.
            WindowConstructions (list of WindowConstruction): list of
                WindowConstruction objects.
            StructureDefinitions (list of StructureDefinition): list of
                StructureDefinition objects.
            DaySchedules (list of DaySchedule): list of DaySchedule objects.
            WeekSchedules (list of WeekSchedule): list of WeekSchedule objects.
            YearSchedules (list of YearSchedule): list of YearSchedule objects.
            DomesticHotWaterSettings (list of DomesticHotWaterSetting): list of
                DomesticHotWaterSetting objects.
            VentilationSettings (list of VentilationSetting): list of
                VentilationSetting objects.
            WindowSettings (list of WindowSetting): list of WindowSetting
                objects.
            ZoneConditionings (list of ZoneConditioning): list of
                ZoneConditioning objects.
            ZoneConstructionSets (list of ZoneConstructionSet): list of
                ZoneConstructionSet objects.
            ZoneLoads (list of ZoneLoad): list of ZoneLoad objects.
            Zones (list of Zone): list of Zone objects
        """
        if Zones is None:
            Zones = []
        if ZoneLoads is None:
            ZoneLoads = []
        if ZoneConstructionSets is None:
            ZoneConstructionSets = []
        if ZoneConditionings is None:
            ZoneConditionings = []
        if WindowSettings is None:
            WindowSettings = []
        if VentilationSettings is None:
            VentilationSettings = []
        if DomesticHotWaterSettings is None:
            DomesticHotWaterSettings = []
        if YearSchedules is None:
            YearSchedules = []
        if WeekSchedules is None:
            WeekSchedules = []
        if DaySchedules is None:
            DaySchedules = []
        if StructureDefinitions is None:
            StructureDefinitions = []
        if WindowConstructions is None:
            WindowConstructions = []
        if OpaqueMaterials is None:
            OpaqueMaterials = []
        if OpaqueConstructions is None:
            OpaqueConstructions = []
        if GlazingMaterials is None:
            GlazingMaterials = []
        if GasMaterials is None:
            GasMaterials = []
        if BuildingTemplates is None:
            BuildingTemplates = []

        self.idfs = None
        self.idf_files = None
        self.name = name
        self.Zones = Zones
        self.ZoneLoads = ZoneLoads
        self.ZoneConstructionSets = ZoneConstructionSets
        self.ZoneConditionings = ZoneConditionings
        self.WindowSettings = WindowSettings
        self.VentilationSettings = VentilationSettings
        self.DomesticHotWaterSettings = DomesticHotWaterSettings
        self.YearSchedules = YearSchedules
        self.WeekSchedules = WeekSchedules
        self.DaySchedules = DaySchedules
        self.StructureDefinitions = StructureDefinitions
        self.WindowConstructions = WindowConstructions
        self.OpaqueMaterials = OpaqueMaterials
        self.OpaqueConstructions = OpaqueConstructions
        self.BuildingTemplates = BuildingTemplates
        self.GasMaterials = GasMaterials
        self.GlazingMaterials = GlazingMaterials

    @classmethod
    def read_idf(
        cls, idf_files, weather, sql=None, name="unnamed", load_idf_kwargs=None
    ):
        """Initializes an UmiTemplate object from one or more idf_files.

        The resulting object contains the reduced version of the IDF files.
        To save to file, call the :meth:`to_json` method.

        Args:
            idf_files (str or list): One or more IDF file paths.
            weather (str): Path to the weather file.
            sql:
            name:
            load_idf_kwargs (dict): kwargs passed to the
                :meth:`archetypal.idfclass.load_idf` method.
        """
        if load_idf_kwargs is None:
            load_idf_kwargs = {}
        # instantiate class
        t = cls(name)

        # fill in arguments
        t.idf_files = idf_files
        t.weather = weather
        t.sql = sql

        # Load IDF objects
        t.idfs = [
            load_idf(idf_file, weather_file=weather, **load_idf_kwargs)
            for idf_file in idf_files
        ]

        # For each idf load
        template_obj = []
        for idf in t.idfs:
            bldg = BuildingTemplate.from_idf(idf, sql=idf.sql, DataSource=idf.name)
            template_obj.append(bldg)
            for name in [
                DaySchedule,
                DomesticHotWaterSetting,
                GasMaterial,
                GlazingMaterial,
                OpaqueConstruction,
                OpaqueMaterial,
                StructureDefinition,
                VentilationSetting,
                WeekSchedule,
                WindowConstruction,
                YearSchedule,
                ZoneConditioning,
                ZoneConstructionSet,
                ZoneLoad,
                Zone,
            ]:
                t.__dict__[name.__name__ + "s"].extend(
                    [obj for obj in bldg.all_objects.values() if isinstance(obj, name)]
                )

        t.BuildingTemplates = template_obj

        return t

    @classmethod
    def read_file(cls, filename):
        """Initializes an UmiTemplate object from an UMI Template File.

        Args:
            filename (path-like): Path-like object giving the pathname (absolute
                or relative to the current working directory) of the UMI
                Template File.

        Returns:
            UmiTemplate: The template object.
        """
        name = Path(filename)
        t = cls(name)

        with open(filename, "r") as f:
            import json

            datastore = json.load(f)

            # with datastore, create each objects
            t.GasMaterials = [
                GasMaterial.from_json(**store) for store in datastore["GasMaterials"]
            ]
            t.GlazingMaterials = [
                GlazingMaterial(**store) for store in datastore["GlazingMaterials"]
            ]
            t.OpaqueMaterials = [
                OpaqueMaterial(**store) for store in datastore["OpaqueMaterials"]
            ]
            t.OpaqueConstructions = [
                OpaqueConstruction.from_json(**store)
                for store in datastore["OpaqueConstructions"]
            ]
            t.WindowConstructions = [
                WindowConstruction.from_json(**store)
                for store in datastore["WindowConstructions"]
            ]
            t.StructureDefinitions = [
                StructureDefinition.from_json(**store)
                for store in datastore["StructureDefinitions"]
            ]
            t.DaySchedules = [
                DaySchedule.from_json(**store) for store in datastore["DaySchedules"]
            ]
            t.WeekSchedules = [
                WeekSchedule.from_json(**store) for store in datastore["WeekSchedules"]
            ]
            t.YearSchedules = [
                YearSchedule.from_json(**store) for store in datastore["YearSchedules"]
            ]
            t.DomesticHotWaterSettings = [
                DomesticHotWaterSetting.from_json(**store)
                for store in datastore["DomesticHotWaterSettings"]
            ]
            t.VentilationSettings = [
                VentilationSetting.from_json(**store)
                for store in datastore["VentilationSettings"]
            ]
            t.ZoneConditionings = [
                ZoneConditioning.from_json(**store)
                for store in datastore["ZoneConditionings"]
            ]
            t.ZoneConstructionSets = [
                ZoneConstructionSet.from_json(**store)
                for store in datastore["ZoneConstructionSets"]
            ]
            t.ZoneLoads = [
                ZoneLoad.from_json(**store) for store in datastore["ZoneLoads"]
            ]
            t.Zones = [Zone.from_json(**store) for store in datastore["Zones"]]
            t.BuildingTemplates = [
                BuildingTemplate.from_json(**store)
                for store in datastore["BuildingTemplates"]
            ]

        return t

    def to_json(self, path_or_buf=None, indent=2, all_zones=False, sort_keys=False):
        """Writes the umi template to json format

        Args:
            path_or_buf (path-like): Path-like object giving the pathname
                (absolute or relative to the current working directory)
            indent (bool or str): If indent is a non-negative integer or string,
                then JSON array elements and object members will be
                pretty-printed with that indent level. An indent level of 0,
                negative, or "" will only insert newlines. None (the default)
                selects the most compact representation. Using a positive
                integer indent indents that many spaces per level. If indent is
                a string (such as "t"), that string is used to indent each
                level.
            all_zones (bool): If True, all zones that have participated in the
                creation of the core and perimeter zones will be outputed to the
                json file.
            sort_keys (bool): If sort_keys is true (default: False), then the
                output of dictionaries will be sorted by key; this is useful for
                regression tests to ensure that JSON serializations can be
                compared on a day-to-day basis.
        """
        # todo: check if bools are created as lowercase 'false' or 'true'

        if not path_or_buf:
            json_name = "%s.json" % self.name
            path_or_buf = os.path.join(settings.data_folder, json_name)
            # create the folder on the disk if it doesn't already exist
            if not os.path.exists(settings.data_folder):
                os.makedirs(settings.data_folder)
        with io.open(path_or_buf, "w+", encoding="utf-8") as path_or_buf:
            data_dict = OrderedDict(
                {
                    "GasMaterials": [],
                    "GlazingMaterials": [],
                    "OpaqueMaterials": [],
                    "OpaqueConstructions": [],
                    "WindowConstructions": [],
                    "StructureDefinitions": [],
                    "DaySchedules": [],
                    "WeekSchedules": [],
                    "YearSchedules": [],
                    "DomesticHotWaterSettings": [],
                    "VentilationSettings": [],
                    "ZoneConditionings": [],
                    "ZoneConstructionSets": [],
                    "ZoneLoads": [],
                    "Zones": [],
                    "WindowSettings": [],
                    "BuildingTemplates": [],
                }
            )

            jsonized = {}

            def recursive_json(obj):
                if obj.__class__.mro()[0] == UmiSchedule:
                    obj = obj.develop()
                catname = obj.__class__.__name__ + "s"
                if catname in data_dict:
                    key = obj.id
                    if key not in jsonized.keys():
                        app_dict = obj.to_json()
                        data_dict[catname].append(app_dict)
                        jsonized[key] = obj
                for key, value in obj.__dict__.items():

                    if isinstance(
                        value, (UmiBase, MaterialLayer, YearScheduleParts)
                    ) and not key.startswith("_"):
                        recursive_json(value)
                    elif isinstance(value, list):
                        [
                            recursive_json(value)
                            for value in value
                            if isinstance(
                                value,
                                (UmiBase, MaterialLayer, YearScheduleParts, MassRatio),
                            )
                        ]

            for bld in self.BuildingTemplates:
                if all_zones:
                    recursive_json(bld)
                else:
                    # First, remove cores and perims lists
                    cores = bld.__dict__.pop("cores", None)
                    perims = bld.__dict__.pop("perims", None)

                    # apply the recursion
                    recursive_json(bld)

                    # put back objects
                    bld.cores = cores
                    bld.perims = perims

            for key in data_dict:
                data_dict[key] = sorted(
                    data_dict[key], key=lambda x: x["Name"] if "Name" in x else "A"
                )

            class CustomJSONEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, np.bool_):
                        return bool(obj)

                    return obj

            if not data_dict["GasMaterials"]:
                # Umi needs at least one gas material even if it is not necessary.
                data_dict["GasMaterials"].append(GasMaterial(Name="AIR").to_json())
            # Write the dict to json using json.dumps
            response = json.dumps(
                data_dict, indent=indent, sort_keys=sort_keys, cls=CustomJSONEncoder
            )
            path_or_buf.write(response)

        return response
