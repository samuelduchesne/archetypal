"""UmiTemplateLibrary Module."""

from __future__ import annotations

import json
import logging as lg
from collections import OrderedDict, defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
from typing import ClassVar, Union

import networkx as nx
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
    UmiSchedule,
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


class AllFailedError(Exception):
    """Exception raised when all BuildingTemplates failed to be created."""

    def __init__(self, results):
        super().__init__([res for res in results.values() if isinstance(res, Exception)])


class UmiTemplateLibrary:
    """Handles parsing and creating Template Library Files for UMI for Rhino.

    - See :meth:`open` to parse existing Umi Template Library files (.json).
    - See :meth:`from_idf_files` to create a library by converting existing IDF models.
    """

    _LIB_GROUPS: ClassVar[list[str]] = [
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

    def __getitem__(self, item):
        return self.__dict__[item]

    def __add__(self, other: UmiTemplateLibrary):
        """Combined"""
        for _, group in other:
            # for each group items
            for component in group:
                component.id = None  # Reset the component's id

        attrs = {}
        for group, value in self:
            attrs[group] = value + other.__dict__[group]

        newlib = self.__class__(**attrs, name=self.name)
        newlib.unique_components("GasMaterials", keep_orphaned=True)
        return newlib

    def _clear_components_list(self, except_groups=None):
        """Clear components lists except except_groups."""
        if except_groups is None:
            except_groups = []
        exception = ["BuildingTemplates"]
        exception.extend(except_groups)
        for key, _ in self:
            if key not in exception:
                setattr(self, key, [])

    @property
    def object_list(self):
        """Get list of all objects in self, including orphaned objects."""
        objs = []
        for _, group in self:
            objs.extend(group)
        return objs

    @classmethod
    def from_idf_files(
        cls,
        idf_files,
        weather,
        name="unnamed",
        processors=-1,
        keep_all_zones=False,
        unique_components=None,
        debug=False,
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
            debug (bool): If True, will raise any error on any processed file and
                keep simulation cache directory.
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
                keep_data_err=debug,
                readvars=False,  # No need to readvars since only sql is used
                **kwargs,
            )
        results = parallel_process(
            in_dict,
            cls.template_complexity_reduction,
            processors=processors,
            use_kwargs=True,
            debug=debug,
            position=None,
            executor=ThreadPoolExecutor,
        )
        for filename, res in results.items():
            if isinstance(res, EnergyPlusProcessError):
                filename = settings.logs_folder / "failed_reduce.txt"
                with open(filename, "a") as file:
                    file.writelines(res.write())
                    log(
                        f"EnergyPlusProcess error for {filename} listed in {filename}: {res}",
                        lg.ERROR,
                    )
            elif isinstance(res, Exception):
                if debug:
                    raise res
                else:
                    log(
                        f"Exception raised for {filename}: {res}",
                        lg.ERROR,
                    )

        # If all exceptions, raise them for debugging
        if all(isinstance(x, Exception) for x in results.values()):
            raise AllFailedError(results)

        umi_template.BuildingTemplates = [res for res in results.values() if not isinstance(res, Exception)]

        if keep_all_zones:
            _zones = {obj.get_unique() for obj in ZoneDefinition._CREATED_OBJECTS}
            for zone in _zones:
                umi_template.ZoneDefinitions.append(zone)
            exceptions = [ZoneDefinition.__name__]
        else:
            exceptions = None

        # Get unique instances
        umi_template.unique_components(*(unique_components or []), exceptions=exceptions)

        # Update attributes of instance
        umi_template.update_components_list(exceptions=exceptions)

        return umi_template

    @staticmethod
    def template_complexity_reduction(idfname, epw, **kwargs):
        """Wrap IDF, simulate and BuildingTemplate for parallel processing."""
        idf = IDF(idfname, epw=epw, **kwargs)
        idf._outputs.add_umi_template_outputs()

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

        try:
            idf.simulate()
        except EnergyPlusProcessError as e:
            return e
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
        with open(filename) as f:
            t = cls.loads(f.read(), name)

        return t

    @classmethod
    def loads(cls, s, name):
        """load string."""
        datastore = json.loads(s)
        # with datastore, create each objects
        t = cls(name)
        t.GasMaterials = [GasMaterial.from_dict(store, allow_duplicates=False) for store in datastore["GasMaterials"]]
        t.GlazingMaterials = [
            GlazingMaterial.from_dict(store, allow_duplicates=False) for store in datastore["GlazingMaterials"]
        ]
        t.OpaqueMaterials = [
            OpaqueMaterial.from_dict(store, allow_duplicates=False) for store in datastore["OpaqueMaterials"]
        ]
        t.OpaqueConstructions = [
            OpaqueConstruction.from_dict(
                store,
                materials={a.id: a for a in (t.GasMaterials + t.GlazingMaterials + t.OpaqueMaterials)},
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
        t.DaySchedules = [DaySchedule.from_dict(store, allow_duplicates=True) for store in datastore["DaySchedules"]]
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
                domestic_hot_water_settings={a.id: a for a in t.DomesticHotWaterSettings},
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
        data_dict = OrderedDict([(key, []) for key in self._LIB_GROUPS])

        for group_name, group in self:
            UniqueName.existing = {}
            for obj in group:
                data = obj.to_dict()
                data.update({"Name": UniqueName(data.get("Name"))})
                data_dict[group_name].append(data)

        if not data_dict["GasMaterials"]:
            data = GasMaterial(Name="AIR").to_dict()
            data.update({"Name": UniqueName(data.get("Name"))})
            data_dict["GasMaterials"].append(data)
            data_dict.move_to_end("GasMaterials", last=False)

        for key in list(data_dict.keys()):
            if key == "ZoneDefinitions":
                data_dict["Zones"] = data_dict.pop(key)
            elif key == "StructureInformations":
                data_dict["StructureDefinitions"] = data_dict.pop(key)

        assert no_duplicates(data_dict, attribute="Name")

        for key in data_dict:
            data_dict[key] = sorted(data_dict[key], key=lambda x: x.get("Name"))

        return data_dict

    def unique_components(self, *args: str, exceptions: list[str] | None = None, keep_orphaned=False):
        """Keep only unique components.

        Starts by clearing all objects in self except self.BuildingTemplates.
        Then, recursively traverses the children of each BuildingTemplate, finding a
        unique object for "equivalent" components.

        Calls :func:`~archetypal.template.umi_base.UmiBase.get_unique` for each
        object in the graph.

        Args:
            *args (str): UmiBase class names that should be replaced with a
                unique equivalent. For example, if only "OpaqueMaterials" should be
                unique, then use self.unique_components("OpaqueMaterials"). If none
                are provided, all umi components be unique.
            exceptions (List[str]): A list of UmiBase class names that will not be
                cleared from self.
            keep_orphaned (bool): if True, orphaned objects are kept.
        """
        if keep_orphaned:
            G = self.to_graph(include_orphans=True)
            connected_to_building = set()
            for bldg in self.BuildingTemplates:
                for obj in nx.dfs_preorder_nodes(G, bldg):
                    connected_to_building.add(obj)
            orphans = [obj for obj in self.object_list if obj not in connected_to_building]
        self._clear_components_list(exceptions)  # First clear components

        # Inclusion is a set of object classes that will be unique.
        inclusion = set(args or [])
        if not inclusion.isdisjoint(set(self._LIB_GROUPS)):
            inclusion = set(self._LIB_GROUPS).intersection(inclusion)
        else:
            if inclusion:
                assert inclusion.intersection(set(self._LIB_GROUPS)), (
                    f"{', '.join(inclusion.difference(set(self._LIB_GROUPS)))} not a "
                    f"valid class name. Valid values are: "
                    f"{', '.join(set(self._LIB_GROUPS))}"
                )
            inclusion = set(self._LIB_GROUPS)
        for key, group in self:
            # for each group
            for component in group:
                # travers each object using generator
                for parent, key, obj in parent_key_child_traversal(component):
                    if obj.__class__.__name__ + "s" in inclusion and key:
                        setattr(parent, key, obj.get_unique())  # set unique object on key

        self.update_components_list(exceptions=exceptions)  # Update the components list
        if keep_orphaned:
            for obj in orphans:
                self[obj.__class__.__name__ + "s"].append(obj)

    def replace_component(self, this, that) -> None:
        """Replace all instances of `this` with `that`.

        Args:
            this (UmiBase): The reference to replace with `that`.
            that (UmiBase): The object to replace each references with.
        """
        for bldg in self.BuildingTemplates:
            for parent, key, obj in parent_key_child_traversal(bldg):
                if obj is this:
                    setattr(parent, key, that)

        self.update_components_list()

    def update_components_list(self, exceptions=None):
        """Update the component groups with connected components."""
        # clear components list except BuildingTemplate
        self._clear_components_list(exceptions)

        for key, group in self:
            for component in group:
                for parent, key, child in parent_key_child_traversal(component):
                    if isinstance(child, UmiSchedule) and not isinstance(
                        child, (DaySchedule, WeekSchedule, YearSchedule)
                    ):
                        y, ws, ds = child.to_year_week_day()
                        if not any(o.id == y.id for o in self.YearSchedules):
                            self.YearSchedules.append(y)
                        for w in ws:
                            if not any(o.id == w.id for o in self.WeekSchedules):
                                self.WeekSchedules.append(w)
                        for d in ds:
                            if not any(o.id == d.id for o in self.DaySchedules):
                                self.DaySchedules.append(d)
                        # finally, replace it with y
                        setattr(parent, key, y)
                    elif isinstance(child, UmiBase):
                        obj_list = self.__dict__[child.__class__.__name__ + "s"]
                        if not any(o.id == child.id for o in obj_list):
                            # Important to compare on UmiBase.id and not on identity.
                            obj_list.append(child)

    def to_graph(self, include_orphans=False):
        """Create a :class:`networkx.DiGraph` of self.

        This networkx.DiGraph object is then useful for graph-theory operations on
        the hierarchy of the UmiTemplateLibrary.
        """
        import networkx as nx

        G = nx.DiGraph()

        for bldg in self.BuildingTemplates:
            for parent, child in parent_child_traversal(bldg):
                if parent:
                    G.add_edge(parent, child)

        if include_orphans:
            orphans = [obj for obj in self.object_list if obj.id not in (n.id for n in G)]
            for orphan in orphans:
                G.add_node(orphan)
                for parent, child in parent_child_traversal(orphan):
                    if parent:
                        G.add_edge(parent, child)

        return G


def no_duplicates(file: Union[str, dict], attribute="Name"):
    """Assert whether or not dict has duplicated Names."""

    if isinstance(file, str):
        with open(file) as f:
            data = json.loads(f.read())
    else:
        data = file
    ids = defaultdict(lambda: defaultdict(int))

    for key, value in data.items():
        for component in value:
            _id = component.get(attribute)
            if _id:
                ids[key][_id] += 1

    dups = {
        key: {k: v for k, v in values.items() if v > 1}
        for key, values in ids.items()
        if any(v > 1 for v in values.values())
    }

    if dups:
        raise DuplicateAttributeError(attribute, dups)
    return True


class DuplicateAttributeError(Exception):
    """Exception raised for duplicate attributes in UMI objects."""

    def __init__(self, attribute, duplicates):
        """Initialize a DuplicateAttributeError."""
        super().__init__(f"Duplicate {attribute} found: {duplicates}")


DEEP_OBJECTS = (UmiBase, MaterialLayer, GasLayer, YearSchedulePart, MassRatio, list)


def parent_key_child_traversal(parent):
    """Iterate over children of parent yield the parent, the attribute name of the
    children (key) and the children itself.

    If called on a :class:BuildingTemplate object, this will traverse all the
    umi components this object references, like a depth-first search algotrithm in a
    graph structure.
    """
    if isinstance(parent, DEEP_OBJECTS):
        if isinstance(parent, list):
            for obj in parent:
                yield from parent_key_child_traversal(obj)
        elif isinstance(parent, DaySchedule):
            yield None, None, parent
        else:
            for k, child in parent:
                if isinstance(child, UmiBase):
                    yield parent, k, child
                if isinstance(child, DEEP_OBJECTS):
                    yield from parent_key_child_traversal(child)


def parent_child_traversal(parent: UmiBase):
    """Iterate over all children of the parent.

    This generator recursively yields (parent, child) tuples. It uses the
    :attr:`UmiBase.children` attribute and had a better performance than
    :func:`parent_key_child_traversal`.
    """
    for child in parent.children:
        yield parent, child
        yield from parent_child_traversal(child)


def traverse(parent):
    return parent_child_traversal(parent)
