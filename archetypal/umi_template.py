"""UmiTemplateLibrary Module."""

import json
import logging as lg
from collections import OrderedDict
from concurrent.futures.thread import ThreadPoolExecutor

from pandas.io.common import get_handle
from path import Path

from archetypal import settings
from archetypal.eplus_interface.exceptions import EnergyPlusProcessError
from archetypal.idfclass.idf import IDF
from archetypal.template.building_template import BuildingTemplate
from archetypal.template.conditioning import ZoneConditioning
from archetypal.template.constructions.opaque_construction import OpaqueConstruction
from archetypal.template.constructions.window_construction import WindowConstruction
from archetypal.template.dhw import DomesticHotWaterSetting
from archetypal.template.load import ZoneLoad
from archetypal.template.materials.gas_layer import GasLayer
from archetypal.template.materials.gas_material import GasMaterial
from archetypal.template.materials.glazing_material import GlazingMaterial
from archetypal.template.materials.material_layer import MaterialLayer
from archetypal.template.materials.opaque_material import OpaqueMaterial
from archetypal.template.schedule import (
    DaySchedule,
    WeekSchedule,
    YearSchedule,
    YearSchedulePart,
)
from archetypal.template.structure import MassRatio, StructureInformation
from archetypal.template.umi_base import UmiBase, UniqueName
from archetypal.template.ventilation import VentilationSetting
from archetypal.template.window_setting import WindowSetting
from archetypal.template.zone_construction_set import ZoneConstructionSet
from archetypal.template.zonedefinition import ZoneDefinition
from archetypal.utils import CustomJSONEncoder, log, parallel_process


class UmiTemplateLibrary:
    """Handles parsing and creating Template Library Files for UMI for Rhino.

    - See :meth:`open` to parse existing Umi Template Library files (.json).
    - See :meth:`from_idf_files` to create a library by converting existing IDF models.
    """

    _LIB_GROUPS = [
        "GasMaterials",
        "GlazingMaterials",
        "OpaqueMaterials",
        "OpaqueConstructions",
        "WindowConstructions",
        "StructureInformations",
        "DaySchedules",
        "WeekSchedules",
        "YearSchedules",
        "DomesticHotWaterSettings",
        "VentilationSettings",
        "ZoneConditionings",
        "ZoneConstructionSets",
        "ZoneLoads",
        "ZoneDefinitions",
        "WindowSettings",
        "BuildingTemplates",
    ]

    def __init__(
        self,
        name="unnamed",
        BuildingTemplates=None,
        GasMaterials=None,
        GlazingMaterials=None,
        OpaqueConstructions=None,
        OpaqueMaterials=None,
        WindowConstructions=None,
        StructureInformations=None,
        DaySchedules=None,
        WeekSchedules=None,
        YearSchedules=None,
        DomesticHotWaterSettings=None,
        VentilationSettings=None,
        WindowSettings=None,
        ZoneConditionings=None,
        ZoneConstructionSets=None,
        ZoneLoads=None,
        ZoneDefinitions=None,
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
            StructureInformations (list of StructureInformation): list of
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
            ZoneDefinitions (list of ZoneDefinition): list of Zone objects
        """
        self.idf_files = []
        self.name = name
        self.ZoneDefinitions = ZoneDefinitions or []
        self.ZoneLoads = ZoneLoads or []
        self.ZoneConstructionSets = ZoneConstructionSets or []
        self.ZoneConditionings = ZoneConditionings or []
        self.WindowSettings = WindowSettings or []
        self.VentilationSettings = VentilationSettings or []
        self.DomesticHotWaterSettings = DomesticHotWaterSettings or []
        self.UmiSchedules = []  # placeholder for UmiSchedules
        self.YearSchedules = YearSchedules or []
        self.WeekSchedules = WeekSchedules or []
        self.DaySchedules = DaySchedules or []
        self.StructureInformations = StructureInformations or []
        self.WindowConstructions = WindowConstructions or []
        self.OpaqueMaterials = OpaqueMaterials or []
        self.OpaqueConstructions = OpaqueConstructions or []
        self.BuildingTemplates = BuildingTemplates or []
        self.GasMaterials = GasMaterials or []
        self.GlazingMaterials = GlazingMaterials or []

    def __iter__(self):
        """Iterate over component groups. Yields tuple of (group, value)."""
        for group in self._LIB_GROUPS:
            yield group, self.__dict__[group]

    def _clear_components_list(self, except_groups=None):
        """Clear components lists except except_groups."""
        if except_groups is None:
            except_groups = []
        exception = ["BuildingTemplates"]
        exception.extend(except_groups)
        for key, group in self:
            if key not in exception:
                setattr(self, key, [])

    @classmethod
    def from_idf_files(
        cls,
        idf_files,
        weather,
        name="unnamed",
        processors=-1,
        keep_all_zones=False,
        **kwargs,
    ):
        """Initialize an UmiTemplateLibrary object from one or more idf_files.

        The resulting object contains the reduced version of the IDF files.
        To save to file, call the :meth:`save` method.

        Important:
            When using :meth:`from_idf_files` The idf files are striped of run period
            modifiers and special days to return simple annual schedules.

        Args:
            idf_files (list of (str or Path)): list of IDF file paths.
            weather (str or Path): Path to the weather file.
            name (str): The name of the Template File
            processors (int): Number of cores. Defaults to -1, all cores.
            kwargs: keyword arguments passed to IDF().

        Raises:
            Exception: All exceptions are raised if settings.debug=True. Will raise
                an exception if all BuildingTemplates failed to be created.
        """
        # instantiate class
        umi_template = cls(name)

        # if parallel is True, run eplus in parallel
        in_dict = {}
        for i, idf_file in enumerate(idf_files):
            in_dict[idf_file] = dict(
                idfname=idf_file,
                epw=weather,
                verbose=False,
                position=i,
                nolimit=True,
                keep_data_err=True,  # For debugging
                readvars=False,  # No need to readvars since only sql is used
                **kwargs,
            )
        results = parallel_process(
            in_dict,
            cls.template_complexity_reduction,
            processors=processors,
            use_kwargs=True,
            debug=True,
            position=None,
            executor=ThreadPoolExecutor,
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

        # If all exceptions, raise them for debugging
        if all(isinstance(x, Exception) for x in results):
            raise Exception([res for res in results if isinstance(res, Exception)])

        umi_template.BuildingTemplates = [
            res for res in results if not isinstance(res, Exception)
        ]

        if keep_all_zones:
            _zones = set(
                obj.get_unique()
                for obj in UmiBase.CREATED_OBJECTS
                if isinstance(obj, ZoneDefinition)
            )
            for zone in _zones:
                umi_template.ZoneDefinitions.append(zone)
            exceptions = [ZoneDefinition.__name__]
        else:
            exceptions = None

        # Get unique instances
        umi_template.unique_components(exceptions)

        # Update attributes of instance
        umi_template.update_components_list(exceptions=exceptions)

        return umi_template

    @staticmethod
    def template_complexity_reduction(idfname, epw, **kwargs):
        """Wrap IDF, simulate and BuildingTemplate for parallel processing."""
        idf = IDF(idfname, epw=epw, **kwargs)

        # remove daylight saving time modifiers
        for daylight in idf.idfobjects["RunPeriodControl:DaylightSavingTime".upper()]:
            idf.removeidfobject(daylight)
        # edit run period to start on Monday
        for run_period in idf.idfobjects["RunPeriod".upper()]:
            run_period.Day_of_Week_for_Start_Day = "Monday"
            run_period.Apply_Weekend_Holiday_Rule = "No"
            run_period.Use_Weather_File_Holidays_and_Special_Days = "No"
            run_period.Use_Weather_File_Daylight_Saving_Period = "No"
        # remove daylight saving time modifiers
        for day in idf.idfobjects["RunPeriodControl:SpecialDays".upper()]:
            idf.removeidfobject(day)

        if idf.sim_info is None:
            idf.simulate()
        return BuildingTemplate.from_idf(idf, **kwargs)

    @classmethod
    def open(cls, filename):
        """Initialize an UmiTemplate object from an UMI Template Library File.

        Args:
            filename (str or Path): PathLike object giving the pathname of the UMI
                Template File.

        Returns:
            UmiTemplateLibrary: The template object.
        """
        name = Path(filename)
        with open(filename, "r") as f:
            t = cls.loads(f.read(), name)

        return t

    @classmethod
    def loads(cls, s, name):
        """load string."""
        datastore = json.loads(s)
        # with datastore, create each objects
        t = cls(name)
        t.GasMaterials = [
            GasMaterial.from_dict(store, allow_duplicates=True)
            for store in datastore["GasMaterials"]
        ]
        t.GlazingMaterials = [
            GlazingMaterial.from_dict(
                store,
            )
            for store in datastore["GlazingMaterials"]
        ]
        t.OpaqueMaterials = [
            OpaqueMaterial.from_dict(store, allow_duplicates=True)
            for store in datastore["OpaqueMaterials"]
        ]
        t.OpaqueConstructions = [
            OpaqueConstruction.from_dict(
                store,
                materials={
                    a.id: a
                    for a in (t.GasMaterials + t.GlazingMaterials + t.OpaqueMaterials)
                },
                allow_duplicates=True,
            )
            for store in datastore["OpaqueConstructions"]
        ]
        t.WindowConstructions = [
            WindowConstruction.from_dict(
                store,
                materials={a.id: a for a in (t.GasMaterials + t.GlazingMaterials)},
                allow_duplicates=True,
            )
            for store in datastore["WindowConstructions"]
        ]
        t.StructureInformations = [
            StructureInformation.from_dict(
                store,
                materials={a.id: a for a in t.OpaqueMaterials},
                allow_duplicates=True,
            )
            for store in datastore["StructureDefinitions"]
        ]
        t.DaySchedules = [
            DaySchedule.from_dict(store, allow_duplicates=True)
            for store in datastore["DaySchedules"]
        ]
        t.WeekSchedules = [
            WeekSchedule.from_dict(
                store,
                day_schedules={a.id: a for a in t.DaySchedules},
                allow_duplicates=True,
            )
            for store in datastore["WeekSchedules"]
        ]
        t.YearSchedules = [
            YearSchedule.from_dict(
                store,
                week_schedules={a.id: a for a in t.WeekSchedules},
                allow_duplicates=True,
            )
            for store in datastore["YearSchedules"]
        ]
        t.DomesticHotWaterSettings = [
            DomesticHotWaterSetting.from_dict(
                store,
                schedules={a.id: a for a in t.YearSchedules},
                allow_duplicates=True,
            )
            for store in datastore["DomesticHotWaterSettings"]
        ]
        t.VentilationSettings = [
            VentilationSetting.from_dict(
                store,
                schedules={a.id: a for a in t.YearSchedules},
                allow_duplicates=True,
            )
            for store in datastore["VentilationSettings"]
        ]
        t.ZoneConditionings = [
            ZoneConditioning.from_dict(
                store,
                schedules={a.id: a for a in t.YearSchedules},
                allow_duplicates=True,
            )
            for store in datastore["ZoneConditionings"]
        ]
        t.ZoneConstructionSets = [
            ZoneConstructionSet.from_dict(
                store,
                opaque_constructions={a.id: a for a in t.OpaqueConstructions},
                allow_duplicates=True,
            )
            for store in datastore["ZoneConstructionSets"]
        ]
        t.ZoneLoads = [
            ZoneLoad.from_dict(
                store,
                schedules={a.id: a for a in t.YearSchedules},
                allow_duplicates=True,
            )
            for store in datastore["ZoneLoads"]
        ]
        t.ZoneDefinitions = [
            ZoneDefinition.from_dict(
                store,
                zone_conditionings={a.id: a for a in t.ZoneConditionings},
                zone_construction_sets={a.id: a for a in t.ZoneConstructionSets},
                domestic_hot_water_settings={
                    a.id: a for a in t.DomesticHotWaterSettings
                },
                opaque_constructions={a.id: a for a in t.OpaqueConstructions},
                zone_loads={a.id: a for a in t.ZoneLoads},
                ventilation_settings={a.id: a for a in t.VentilationSettings},
                allow_duplicates=True,
            )
            for store in datastore["Zones"]
        ]
        t.WindowSettings = [
            WindowSetting.from_ref(
                store["$ref"],
                datastore["BuildingTemplates"],
                schedules={a.id: a for a in t.YearSchedules},
                window_constructions={a.id: a for a in t.WindowConstructions},
            )
            if "$ref" in store
            else WindowSetting.from_dict(
                store,
                schedules={a.id: a for a in t.YearSchedules},
                window_constructions={a.id: a for a in t.WindowConstructions},
                allow_duplicates=True,
            )
            for store in datastore["WindowSettings"]
        ]
        t.BuildingTemplates = [
            BuildingTemplate.from_dict(
                store,
                zone_definitions={a.id: a for a in t.ZoneDefinitions},
                structure_definitions={a.id: a for a in t.StructureInformations},
                window_settings={a.id: a for a in t.WindowSettings},
                schedules={a.id: a for a in t.YearSchedules},
                window_constructions={a.id: a for a in t.WindowConstructions},
                allow_duplicates=True,
            )
            for store in datastore["BuildingTemplates"]
        ]
        return t

    def validate(self, defaults=True):
        """Validate the object."""
        pass

    def save(
        self,
        path_or_buf=None,
        indent=2,
        sort_keys=False,
        compression="infer",
        storage_options=None,
    ):
        """Save to json file.

        Args:
            path_or_buf (path-like): File path or object. If not specified,
                overwrites files. See :attr:`UmiTemplateLibrary.name`.
            indent (bool or str or int): If indent is a non-negative integer or string,
                then JSON array elements and object members will be
                pretty-printed with that indent level. An indent level of 0,
                negative, or "" will only insert newlines. None (the default)
                selects the most compact representation. Using a positive
                integer indent indents that many spaces per level. If indent is
                a string (such as "t"), that string is used to indent each
                level.
            sort_keys (callable): If sort_keys is true (default: False), then the
                output of dictionaries will be sorted by this callable.
                e.g.: `lambda x: x.get("$id")` sorts by $id. If callable is not
                available or fails, then sorted by `Name`.
            compression (str): A string representing the compression to use in the
                output file, only used when the first argument is a filename. By
                default, the compression is inferred from the filename.
            storage_options (dict): Extra options that make sense for a particular
                storage connection, e.g. host, port, username, password, etc.,
                if using a URL that will be parsed by fsspec, e.g., starting “s3://”,
                “gcs://”. An error will be raised if providing this argument with a
                non-fsspec URL. See the fsspec and backend storage implementation
                docs for the set of allowed keys and values.
        """
        if path_or_buf is None:
            basedir = Path(self.name).dirname()
            name = Path(self.name).stem
            path_or_buf = basedir / name + ".json"

        self.to_json(
            path_or_buf,
            indent=indent,
            sort_keys=sort_keys,
            compression=compression,
            storage_options=storage_options,
        )

    def to_json(
        self,
        path_or_buf=None,
        indent=2,
        sort_keys=False,
        default_handler=None,
        compression="infer",
        storage_options=None,
    ):
        """Convert the object to a JSON string.

        Args:
            path_or_buf (path-like): File path or object. If not specified,
                the result is returned as a string.
            indent (bool or str or int): If indent is a non-negative integer or string,
                then JSON array elements and object members will be
                pretty-printed with that indent level. An indent level of 0,
                negative, or "" will only insert newlines. None (the default)
                selects the most compact representation. Using a positive
                integer indent indents that many spaces per level. If indent is
                a string (such as "t"), that string is used to indent each
                level.
            sort_keys (callable):
            default_handler (callable): Handler to call if object cannot otherwise be
                converted to a suitable format for JSON. Should receive a single
                argument which is the object to convert and return a serializable
                object.
            compression (str): A string representing the compression to use in the
                output file, only used when the first argument is a filename. By
                default, the compression is inferred from the filename.
            storage_options (dict): Extra options that make sense for a particular
                storage connection, e.g. host, port, username, password, etc.,
                if using a URL that will be parsed by fsspec, e.g., starting “s3://”,
                “gcs://”. An error will be raised if providing this argument with a
                non-fsspec URL. See the fsspec and backend storage implementation
                docs for the set of allowed keys and values.
        """
        if default_handler is None:
            default_handler = CustomJSONEncoder

        data_dict = self.to_dict()

        if sort_keys is not None:
            # Sort values
            for key in data_dict:
                # Sort the list elements by their Name
                try:
                    data_dict[key] = sorted(data_dict[key], key=sort_keys)
                except Exception:
                    # revert to sorting by Name if failure
                    data_dict[key] = sorted(data_dict[key], key=lambda x: x.get("Name"))

        response = json.dumps(data_dict, indent=indent, cls=default_handler)
        if path_or_buf is not None:
            # apply compression and byte/text conversion
            with get_handle(
                path_or_buf,
                "wt",
                compression=compression,
                storage_options=storage_options,
            ) as handles:
                handles.handle.write(response)
        else:
            return response

    def to_dict(self):
        """Return UmiTemplateLibrary dictionary representation."""
        # First, reset existing name

        # Create ordered dict with empty list
        data_dict = OrderedDict([(key, []) for key in self._LIB_GROUPS])

        # create dict values
        for group_name, group in self:
            # reset unique names for group
            UniqueName.existing = set()
            obj: UmiBase
            for obj in group:
                data = obj.to_dict()
                data.update({"Name": UniqueName(data.get("Name"))})
                data_dict.setdefault(group_name, []).append(data)

        if not data_dict.get("GasMaterials"):
            # Umi needs at least one gas material even if it is not necessary.
            data = GasMaterial(Name="AIR").to_dict()
            data.update({"Name": UniqueName(data.get("Name"))})
            data_dict.get("GasMaterials").append(data)
            data_dict.move_to_end("GasMaterials", last=False)

        # Correct naming convention and reorder categories
        for key in tuple(data_dict.keys()):
            v = data_dict[key]
            del data_dict[key]
            if key == "ZoneDefinitions":
                key = "Zones"
            if key == "StructureInformations":
                key = "StructureDefinitions"
            data_dict[key] = v

        # Validate
        assert no_duplicates(data_dict, attribute="Name")

        # Sort values
        for key in data_dict:
            # Sort the list elements by their Name
            data_dict[key] = sorted(data_dict[key], key=lambda x: x.get("Name"))

        return data_dict

    def unique_components(self, exceptions=None):
        """Keep only unique components.

        Calls :func:`~archetypal.template.umi_base.UmiBase.get_unique` for each
        object in the graph.
        """
        self._clear_components_list(exceptions)  # First clear components

        for key, group in self:
            # for each group
            for component in group:
                # travers each object using generator
                for parent, key, obj in traverse(component):
                    if key:  # key is None when we reach lowest level
                        setattr(
                            parent, key, obj.get_unique()
                        )  # set unique object on key

        self.update_components_list(exceptions=exceptions)  # Update the components list
        # that was cleared

    def replace_component(self, this, that) -> None:
        """Replace all instances of `this` with `that`.

        Args:
            this (UmiBase): The reference to replace with `that`.
            that (UmiBase): The object to replace each references with.
        """
        for bldg in self.BuildingTemplates:
            for parent, key, obj in traverse(bldg):
                if obj is this:
                    setattr(parent, key, that)

        self.update_components_list()

    def update_components_list(self, exceptions=None):
        """Update the component groups with connected components."""
        # clear components list except BuildingTemplate
        self._clear_components_list(exceptions)

        for key, group in self:
            for component in group:
                for parent, key, child in traverse(component):
                    if isinstance(child, UmiBase):
                        obj_list = self.__dict__[child.__class__.__name__ + "s"]
                        if not any(o.id == child.id for o in obj_list):
                            # Important to compare on UmiBase.id and not on identity.
                            obj_list.append(child)

    def build_graph(self):
        """Create the :class:`networkx.DiGraph` UmiBase objects as nodes."""
        import networkx as nx

        G = nx.DiGraph()

        for bldg in self.BuildingTemplates:
            for parent, key, child in traverse(bldg):
                G.add_edge(parent, child)

        return G


def no_duplicates(file, attribute="Name"):
    """Assert whether or not dict has duplicated Names.

    `attribute` can be another attribute name like "$id".

    Args:
        file (str or dict): Path of the json file or dict containing umi objects groups
        attribute (str): Attribute to search for duplicates in json UMI structure.
            eg. : "$id", "Name".

    Returns:
        bool: True if no duplicates.

    Raises:
        Exception if duplicates found.
    """
    import json
    from collections import defaultdict

    if isinstance(file, str):
        data = json.loads(open(file).read())
    else:
        data = file
    ids = {}
    for key, value in data.items():
        ids[key] = defaultdict(int)
        for component in value:
            try:
                _id = component[attribute]
            except KeyError:
                pass  # BuildingTemplate does not have an id
            else:
                ids[key][_id] += 1
    dups = {
        key: dict(filter(lambda x: x[1] > 1, values.items()))
        for key, values in ids.items()
        if dict(filter(lambda x: x[1] > 1, values.items()))
    }
    if any(dups.values()):
        raise Exception(f"Duplicate {attribute} found: {dups}")
    else:
        return True


DEEP_OBJECTS = (UmiBase, MaterialLayer, GasLayer, YearSchedulePart, MassRatio, list)


def traverse(parent):
    """Iterate over UmiBases in a depth-first-search (DFS).

    Perform a depth-first-search over the UmiBase objects of var and
    yield the Umibase objects in order.
    """
    if isinstance(parent, DEEP_OBJECTS):
        if isinstance(parent, list):
            for obj in parent:
                yield from traverse(obj)
        elif isinstance(parent, DaySchedule):
            yield None, None, parent
        else:
            for k, child in parent:
                if isinstance(child, UmiBase):
                    yield parent, k, child
                if isinstance(child, DEEP_OBJECTS):
                    yield from traverse(child)
