import io
import json
import logging as lg
import os
from collections import OrderedDict

import numpy as np
from path import Path

from archetypal import IDF, EnergyPlusProcessError, log, parallel_process
from archetypal.template import (
    CREATED_OBJECTS,
    BuildingTemplate,
    DaySchedule,
    DomesticHotWaterSetting,
    GasMaterial,
    GlazingMaterial,
    MassRatio,
    MaterialLayer,
    OpaqueConstruction,
    OpaqueMaterial,
    StructureInformation,
    UmiBase,
    UmiSchedule,
    VentilationSetting,
    WeekSchedule,
    WindowConstruction,
    WindowSetting,
    YearSchedule,
    YearSchedulePart,
    ZoneConditioning,
    ZoneConstructionSet,
    ZoneDefinition,
    ZoneLoad,
    settings,
    UniqueName,
)


class UmiTemplateLibrary:
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
        """Initialize a new UmiTemplateLibrary with empty attributes.

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
            StructureDefinitions (list of StructureInformation): list of
                StructureInformation objects.
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
            Zones (list of ZoneDefinition): list of Zone objects
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
    def read_idf(cls, idf_files, weather, name="unnamed", processors=-1, **kwargs):
        """Initializes an UmiTemplateLibrary object from one or more idf_files.

        The resulting object contains the reduced version of the IDF files.
        To save to file, call the :meth:`to_json` method.

        Args:
            idf_files (list of (str or Path)): list of IDF file paths.
            weather (str or Path): Path to the weather file.
            name (str): The name of the Template File
            parallel (bool): If True, uses all available logical cores.
            kwargs: keyword arguments passed to IDF().

        Raises:
            Exception: All exceptions are raised if settings.debug=True. Will raise
                an exception if all BuildingTemplates failed to be created.
        """
        # instantiate class
        umi_template = cls(name)

        # fill in arguments
        umi_template.idf_files = [Path(idf) for idf in idf_files]
        umi_template.weather = Path(weather).expand()

        # if parallel is True, run eplus in parallel
        in_dict = {}
        for i, idf_file in enumerate(umi_template.idf_files):
            in_dict[idf_file] = dict(
                idfname=idf_file,
                epw=umi_template.weather,
                verbose=False,
                position=None,
                nolimit=True,
                keep_data_err=True,
                **kwargs,
            )
        results = parallel_process(
            in_dict,
            cls.template_complexity_reduction,
            processors=processors,
            use_kwargs=True,
            debug=True,
            position=None,
        )
        for res in results:
            if isinstance(res, EnergyPlusProcessError):
                filename = (settings.logs_folder / "failed_reduce.txt").expand()
                with open(filename, "a") as file:
                    file.writelines(res.write())
                    log(f"EnergyPlusProcess errors listed in {filename}")
            elif isinstance(res, Exception):
                if settings.debug:
                    raise res
                else:
                    log(
                        f"Unable to create Building Template. Exception raised: "
                        f"{str(res)}",
                        lg.ERROR,
                    )

        if all(isinstance(x, Exception) for x in results):
            raise Exception("Complexity reduction failed for all buildings.")

        umi_template.BuildingTemplates = [
            res for res in results if not isinstance(res, Exception)
        ]

        return umi_template

    @staticmethod
    def template_complexity_reduction(idfname, epw, **kwargs):
        idf = IDF(idfname, epw=epw, **kwargs)
        if not idf.simulation_dir.exists():
            idf.simulate()
        return BuildingTemplate.from_idf(idf, **kwargs)

    @classmethod
    def read_file(cls, filename, idf=None):
        """Initializes an UmiTemplate object from an UMI Template File.

        Args:
            filename (str or Path): PathLike object giving the pathname (absolute
                or relative to the current working directory) of the UMI
                Template File.

        Returns:
            UmiTemplateLibrary: The template object.
        """
        name = Path(filename)
        t = cls(name)
        if not idf:
            idf = IDF(prep_outputs=False)
        with open(filename, "r") as f:
            import json

            datastore = json.load(f)

            # with datastore, create each objects
            t.GasMaterials = [
                GasMaterial.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["GasMaterials"]
            ]
            t.GlazingMaterials = [
                GlazingMaterial(**store, idf=idf, allow_duplicates=True)
                for store in datastore["GlazingMaterials"]
            ]
            t.OpaqueMaterials = [
                OpaqueMaterial(**store, idf=idf, allow_duplicates=True)
                for store in datastore["OpaqueMaterials"]
            ]
            t.OpaqueConstructions = [
                OpaqueConstruction.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["OpaqueConstructions"]
            ]
            t.WindowConstructions = [
                WindowConstruction.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["WindowConstructions"]
            ]
            t.StructureDefinitions = [
                StructureInformation.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["StructureDefinitions"]
            ]
            t.DaySchedules = [
                DaySchedule.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["DaySchedules"]
            ]
            t.WeekSchedules = [
                WeekSchedule.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["WeekSchedules"]
            ]
            t.YearSchedules = [
                YearSchedule.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["YearSchedules"]
            ]
            t.DomesticHotWaterSettings = [
                DomesticHotWaterSetting.from_dict(
                    **store, idf=idf, allow_duplicates=True
                )
                for store in datastore["DomesticHotWaterSettings"]
            ]
            t.VentilationSettings = [
                VentilationSetting.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["VentilationSettings"]
            ]
            t.ZoneConditionings = [
                ZoneConditioning.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["ZoneConditionings"]
            ]
            t.ZoneConstructionSets = [
                ZoneConstructionSet.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["ZoneConstructionSets"]
            ]
            t.ZoneLoads = [
                ZoneLoad.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["ZoneLoads"]
            ]
            t.Zones = [
                ZoneDefinition.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["Zones"]
            ]
            t.WindowSettings = [
                WindowSetting.from_ref(
                    store["$ref"], datastore["BuildingTemplates"], idf=idf
                )
                if "$ref" in store
                else WindowSetting.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["WindowSettings"]
            ]
            t.BuildingTemplates = [
                BuildingTemplate.from_dict(**store, idf=idf, allow_duplicates=True)
                for store in datastore["BuildingTemplates"]
            ]

        return t

    def validate(self, defaults=True):
        pass

    def to_json(
        self,
        path_or_buf=None,
        indent=2,
        all_zones=False,
        sort_keys=False,
        include_orphaned=False,
    ):
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
            data_dict = self.to_dict(all_zones, include_orphaned=include_orphaned)

            class CustomJSONEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, np.bool_):
                        return bool(obj)

                    return obj

            response = json.dumps(
                data_dict, indent=indent, sort_keys=sort_keys, cls=CustomJSONEncoder
            )
            path_or_buf.write(response)

        return response

    def to_dict(self, all_zones=False, include_orphaned=False):
        """
        Args:
            all_zones (bool): If True, all zones that have participated in the
                creation of the core and perimeter zones will be outputed to the
                json file.
            include_orphaned (boll): If True, will recursively create all created
                UmiBase objects during session, which could include orphaned
                components (not used by any other parent component).
        """
        # First, reset existing name
        UniqueName.existing = []

        data_dict = OrderedDict(
            {
                "GasMaterials": [],
                "GlazingMaterials": [],
                "OpaqueMaterials": [],
                "OpaqueConstructions": [],
                "WindowConstructions": [],
                "StructureInformations": [],
                "DaySchedules": [],
                "WeekSchedules": [],
                "YearSchedules": [],
                "DomesticHotWaterSettings": [],
                "VentilationSettings": [],
                "ZoneConditionings": [],
                "ZoneConstructionSets": [],
                "ZoneLoads": [],
                "ZoneDefinitions": [],
                "WindowSettings": [],
                "BuildingTemplates": [],
            }
        )
        order = tuple(data_dict.keys())
        jsonized = {}

        def recursive_json(obj):
            if obj.__class__.mro()[0] == UmiSchedule:
                obj = obj.develop()
            catname = obj.__class__.__name__ + "s"
            if catname in data_dict:
                key = obj.id
                if key not in jsonized.keys():
                    try:
                        app_dict = obj.to_json()
                    except AttributeError as e:
                        raise Exception(f"Object '{obj}' raised exception: {str(e)}")
                    data_dict[catname].append(app_dict)
                    jsonized[key] = obj
            for key, value in obj.mapping().items():
                if isinstance(
                    value, (UmiBase, MaterialLayer, YearSchedulePart, MassRatio)
                ):
                    recursive_json(value)
                elif isinstance(value, list):
                    [
                        recursive_json(value)
                        for value in value
                        if isinstance(
                            value,
                            (UmiBase, MaterialLayer, YearSchedulePart, MassRatio),
                        )
                    ]

        if include_orphaned:
            for obj in [obj.get_unique() for obj in CREATED_OBJECTS]:
                recursive_json(obj)
        else:
            for bld in self.BuildingTemplates:
                if all_zones:
                    recursive_json(bld)
                else:
                    # First, remove cores and perims lists
                    cores = bld.__dict__.pop("cores", None)
                    perims = bld.__dict__.pop("perims", None)

                    # apply the recursion
                    recursive_json(bld.get_unique())

                    # put back objects
                    bld.cores = cores
                    bld.perims = perims
        for key in data_dict:
            # Sort the list elements by $id
            data_dict[key] = sorted(data_dict[key], key=lambda x: int(x.get("$id", 0)))

        # Correct naming convention and reorder categories
        if not data_dict.get("GasMaterials"):
            # Umi needs at least one gas material even if it is not necessary.
            data_dict.get("GasMaterials").append(GasMaterial(Name="AIR").to_json())
            data_dict.move_to_end("GasMaterials", last=False)

        for key in order:
            v = data_dict[key]
            del data_dict[key]
            if key == "ZoneDefinitions":
                key = "Zones"
            if key == "StructureInformations":
                key = "StructureDefinitions"
            data_dict[key] = v

        return data_dict
