################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import logging as lg
import time
from itertools import chain, repeat

import networkx
from path import Path
from sigfig import round
from tqdm import tqdm
from validator_collection import validators

from archetypal.template.dhw import DomesticHotWaterSetting
from archetypal.template.materials.material_layer import MaterialLayer
from archetypal.template.schedule import YearSchedulePart
from archetypal.template.structure import MassRatio, StructureInformation
from archetypal.template.umi_base import UmiBase
from archetypal.template.window_setting import WindowSetting
from archetypal.template.zonedefinition import ZoneDefinition
from archetypal.utils import log, reduce


class BuildingTemplate(UmiBase):
    """Main class supporting the definition of a single building template.

    .. image:: ../images/template/buildingtemplate.png
    """

    __slots__ = (
        "_partition_ratio",
        "_lifespan",
        "_core",
        "_perimeter",
        "_structure_definition",
        "_window_setting",
        "_default_window_to_wall_ratio",
        "_year_from",
        "_year_to",
        "_country",
        "_climate_zone",
        "_authors",
        "_author_emails",
        "_version",
    )

    def __init__(
        self,
        Name,
        Core=None,
        Perimeter=None,
        Structure=None,
        Windows=None,
        Lifespan=60,
        PartitionRatio=0.35,
        DefaultWindowToWallRatio=0.4,
        YearFrom=None,
        YearTo=None,
        Country=None,
        ClimateZone=None,
        Authors=None,
        AuthorEmails=None,
        Version="v1.0",
        **kwargs,
    ):
        """Initialize a :class:`BuildingTemplate` object with the following
        attributes:

        Args:
            Core (ZoneDefinition): The Zone object defining the core zone. see
                :class:`Zone` for more details.
            Perimeter (ZoneDefinition): The Zone object defining the perimeter zone. see
                :class:`Zone` for more details.
            Structure (StructureInformation): The StructureInformation object
                defining the structural properties of the template.
            Windows (WindowSetting): The WindowSetting object defining the
                window properties of the object.
            Lifespan (float): The projected lifespan of the building template in
                years. Used in various calculations such as embodied energy.
            PartitionRatio (float): The number of lineal meters of partitions
                (Floor to ceiling) present in average in the building floor plan
                by m2.
            DefaultWindowToWallRatio (float): The default Window to Wall Ratio
                (WWR) for this template (same for all orientations). Number
                between 0 and 1.
            YearFrom (int): Start year for range.
            YearTo (int): End year for range.
            Country (list of str): alpha-3 Country Code.
            ClimateZone (list of str): ANSI/ASHRAE/IESNA Standard 90.1 International
                Climatic Zone. eg. "5A"
            Authors (list of str): Authors of this template
            AuthorEmails (list of str): Contact information.
            Version (str): Version number.
            **kwargs: other optional keywords passed to other constructors.
        """
        super(BuildingTemplate, self).__init__(Name, **kwargs)
        self.PartitionRatio = PartitionRatio
        self.Lifespan = Lifespan
        self.Core = Core
        self.Perimeter = Perimeter
        self.Structure = Structure
        self.Windows = Windows
        self.DefaultWindowToWallRatio = DefaultWindowToWallRatio
        self._year_from = YearFrom  # set privately to allow validation
        self.YearTo = YearTo
        self.Country = Country if Country else []
        self.ClimateZone = ClimateZone if ClimateZone else []
        self.Authors = Authors if Authors else []
        self.AuthorEmails = AuthorEmails if AuthorEmails else []
        self.Version = Version

    @property
    def Perimeter(self):
        """Get or set the perimeter ZoneDefinition."""
        return self._perimeter

    @Perimeter.setter
    def Perimeter(self, value):
        assert isinstance(
            value, ZoneDefinition
        ), f"Expected a ZoneDefinition, not {type(value)}"
        self._perimeter = value

    @property
    def Core(self):
        """Get or set the core ZoneDefinition."""
        return self._core

    @Core.setter
    def Core(self, value):
        assert isinstance(
            value, ZoneDefinition
        ), f"Expected a ZoneDefinition, not {type(value)}"
        self._core = value

    @property
    def Structure(self):
        """Get or set the StructureInformation."""
        return self._structure_definition

    @Structure.setter
    def Structure(self, value):
        assert isinstance(
            value, StructureInformation
        ), f"Expected a StructureInformation, not {type(value)}"
        self._structure_definition = value

    @property
    def Windows(self):
        """Get or set the WindowSetting."""
        return self._window_setting

    @Windows.setter
    def Windows(self, value):
        assert isinstance(
            value, WindowSetting
        ), f"Expected a WindowSetting, not {type(value)}"
        self._window_setting = value

    @property
    def DefaultWindowToWallRatio(self):
        """Get or set the DefaultWindowToWallRatio [-]."""
        return self._default_window_to_wall_ratio

    @DefaultWindowToWallRatio.setter
    def DefaultWindowToWallRatio(self, value):
        self._default_window_to_wall_ratio = validators.float(
            value, minimum=0, maximum=1
        )

    @property
    def Lifespan(self):
        """Get or set the building life span [years]."""
        return self._lifespan

    @Lifespan.setter
    def Lifespan(self, value):
        self._lifespan = validators.integer(value, minimum=True, coerce_value=True)

    @property
    def PartitionRatio(self):
        """Get or set the partition ratio [-]."""
        return self._partition_ratio

    @PartitionRatio.setter
    def PartitionRatio(self, value):
        self._partition_ratio = validators.float(value, minimum=0)

    @property
    def YearFrom(self):
        """Get or set the YearFrom [int]."""
        return self._year_from

    @YearFrom.setter
    def YearFrom(self, value):
        self._year_from = validators.integer(
            value, coerce_value=True, maximum=self.YearTo, allow_empty=True
        )

    @property
    def YearTo(self):
        """Get or set the YearTo [int]."""
        return self._year_to

    @YearTo.setter
    def YearTo(self, value):
        self._year_to = validators.integer(
            value, coerce_value=True, minimum=self.YearFrom, allow_empty=True
        )

    @property
    def Country(self):
        """Get or set the list of alpha-3 country codes [list]."""
        return self._country

    @Country.setter
    def Country(self, value):
        self._country = validators.iterable(value, allow_empty=True)

    @property
    def ClimateZone(self):
        """Get or set the list of climatic zones [list]."""
        return self._climate_zone

    @ClimateZone.setter
    def ClimateZone(self, value):
        self._climate_zone = validators.iterable(value, allow_empty=True)

    @property
    def Authors(self):
        """Get or set the list of authors [list]."""
        return self._authors

    @Authors.setter
    def Authors(self, value):
        self._authors = validators.iterable(value, allow_empty=True)

    @property
    def AuthorEmails(self):
        """Get or set list of author emails [list]."""
        return self._author_emails

    @AuthorEmails.setter
    def AuthorEmails(self, value):
        self._author_emails = validators.iterable(value, allow_empty=True)

    @property
    def Version(self):
        """Get or set the template version [str]."""
        return self._version

    @Version.setter
    def Version(self, value):
        self._version = validators.string(value, coerce_value=True)

    @classmethod
    def from_dict(
        cls,
        data,
        zone_definitions,
        structure_definitions,
        window_settings,
        schedules,
        window_constructions,
        **kwargs,
    ):
        """Create an BuildingTemplate from a dictionary.

        Args:
            data (dict): The python dictionary.
            zone_definitions (dict): A dictionary of ZoneDefinition objects with their
                id as keys.
            structure_definitions (dict): A dictionary of StructureInformation with
                their id as keys.
            window_settings (dict): A dictionary of WindowSetting objects with their
                id as keys.
            schedules (dict): A dictionary of UmiSchedule with their id as keys.
            window_constructions (dict): A dictionary of WindowConstruction objects
                with their id as keys.
            **kwargs: keywords passed to the constructor.

        .. code-block:: python

            {
              "Core": {
                "$ref": "178"
              },
              "Lifespan": 60,
              "PartitionRatio": 0.3,
              "Perimeter": {
                "$ref": "178"
              },
              "Structure": {
                "$ref": "64"
              },
              "Windows": {
                "$ref": "181"
              },
              "DefaultWindowToWallRatio": 0.4,
              "YearFrom": 0,
              "YearTo": 0,
              "Country": [
                "USA"
              ],
              "ClimateZone": [
                "5A"
              ],
              "Authors": [
                "Carlos Cerezo"
              ],
              "AuthorEmails": [
                "ccerezo@mit.edu"
              ],
              "Version": "v1.0",
              "Category": "Residential and Lodging",
              "Comments": "Base building definition for MIT 4433",
              "DataSource": "MIT_SDL",
              "Name": "B_Res_0_WoodFrame"
            }

        """
        core = zone_definitions[data.pop("Core")["$ref"]]
        perim = zone_definitions[data.pop("Perimeter")["$ref"]]
        structure = structure_definitions[data.pop("Structure")["$ref"]]
        window_data = data.pop("Windows")
        try:
            window = window_settings[window_data["$ref"]]
        except KeyError:
            window = WindowSetting.from_dict(
                window_data, schedules, window_constructions
            )

        return cls(
            Core=core,
            Perimeter=perim,
            Structure=structure,
            Windows=window,
            **data,
            **kwargs,
        )

    @classmethod
    def from_idf(cls, idf, **kwargs):
        """Create a BuildingTemplate from an IDF object.

        Args:
            idf (IDF):
            **kwargs:
        """
        # initialize empty BuildingTemplate
        name = kwargs.pop("Name", Path(idf.idfname).basename().splitext()[0])

        epbunch_zones = idf.idfobjects["ZONE"]
        zones = [
            ZoneDefinition.from_epbunch(ep_zone, allow_duplicates=True, **kwargs)
            for ep_zone in tqdm(epbunch_zones, desc=f"Creating UMI objects for {name}")
        ]
        # do core and Perim zone reduction
        bt = cls.reduced_model(name, zones, **kwargs)

        if not bt.Core.DomesticHotWater or not bt.Perimeter.DomesticHotWater:
            dhw = DomesticHotWaterSetting.whole_building(idf)
            if not bt.Core.DomesticHotWater:
                bt.Core.DomesticHotWater = dhw
            if not bt.Perimeter.DomesticHotWater:
                bt.Perimeter.DomesticHotWater = dhw

        bt.Comments = "\n".join(
            [
                "WWR calculated for original model: ",
                idf.wwr().to_string(),
                "where East=90, South=180, West=270, North=0\n",
            ]
        )

        bt.PartitionRatio = idf.partition_ratio

        return bt

    @classmethod
    def reduced_model(cls, name, zones, **kwargs):
        """Create reduced BuildingTemplate from list of ZoneDefinitions.

        Args:
            name (str): The name of the building template.
            zones (list of ZoneDefinition): A list of zone definition objects to
                reduce. At least one must be a perimeter zone (ZoneDefinition.is_core is
                False).
            **kwargs: keywords passed to the class constructor.

        Returns:
            BuildingTemplate: The reduced BuildingTemplate.
        """
        # reduce list of perimeter zones

        log("Initiating complexity reduction...")
        start_time = time.time()

        zone: ZoneDefinition
        cores = list(
            chain.from_iterable(
                [
                    list(repeat(zone.duplicate(), zone.multiplier))
                    for zone in zones
                    if zone.is_core
                ]
            )
        )
        perimeters = list(
            chain.from_iterable(
                [
                    list(repeat(zone.duplicate(), zone.multiplier))
                    for zone in zones
                    if not zone.is_core
                ]
            )
        )
        assert (
            len(perimeters) >= 1
        ), "Building complexity reduction must have at least one perimeter zone."

        Core = None
        # reduce list of core zones
        if cores:
            Core = reduce(
                ZoneDefinition.combine,
                tqdm(
                    cores,
                    desc=f"Reducing core zones in {name}",
                ),
            )
            Core.Name = f"{name}_ZoneDefinition_Core"  # set name

        Perimeter = None
        if perimeters:
            Perimeter = reduce(
                ZoneDefinition.combine,
                tqdm(
                    zones,
                    desc=f"Reducing perimeter zones in {name}",
                ),
            )
            Perimeter.Name = f"{name}_ZoneDefinition_Perimeter"

        # If all perimeter zones, assign self.Perimeter to core.
        if not Core:
            Core = Perimeter
            Core.Name = f"{name}_ZoneDefinition"  # rename as both core/perim

        # resolve StructureInformation and WindowSetting
        structure = StructureInformation(
            MassRatios=[MassRatio.generic()],
            Name=name + "_StructureDefinition",
        )

        # assign generic window if None
        if Perimeter.Windows is None:
            # create generic window
            Perimeter.Windows = WindowSetting.generic(Name="Generic Window")
            kwargs.setdefault("DefaultWindowToWallRatio", 0)

        log(
            f"Equivalent core zone has an area of {Core.area:,.0f} m2",
            level=lg.DEBUG,
        )
        log(
            f"Equivalent perimeter zone has an area of {Perimeter.area:,.0f} m2",
            level=lg.DEBUG,
        )
        log(
            f"Completed model complexity reduction for BuildingTemplate '{name}' "
            f"in {time.time() - start_time:,.2f}"
        )
        return cls(
            name,
            Core=Core,
            Perimeter=Perimeter,
            Windows=Perimeter.Windows,
            Structure=structure,
            **kwargs,
        )

    def _graph_reduce(self, G):
        """Using the depth first search algorithm, iterate over the zone
        adjacency graph and compute the equivalent zone yielded by the
        'addition' of two consecutive zones.

        'Adding' two zones together means both zones properties are
        weighted-averaged by zone area. All dependent objects implement the
        :func:`operator.add` method.

        Args:
            G (archetypal.zone_graph.ZoneGraph):

        Returns:
            ZoneDefinition: The reduced zone
        """
        if len(G) < 1:
            log("No zones for building graph %s" % G.name)
            return None
        else:
            log("starting reduce process for building %s" % self.Name)
            start_time = time.time()

            # start from the highest degree node
            subgraphs = sorted(
                (G.subgraph(c) for c in networkx.connected_components(G)),
                key=len,
                reverse=True,
            )
            from functools import reduce
            from operator import add

            bundle_zone = reduce(
                add,
                [zone for subG in subgraphs for name, zone in subG.nodes(data="zone")],
            )

            log(
                f"completed zone reduction for zone '{bundle_zone.Name}' "
                f"in building '{self.Name}' in {time.time() - start_time:,.2f} seconds"
            )
            return bundle_zone

    def to_dict(self):
        """Return BuildingTemplate dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["Core"] = self.Core.to_ref()
        data_dict["Lifespan"] = self.Lifespan
        data_dict["PartitionRatio"] = round(self.PartitionRatio, 2)
        data_dict["Perimeter"] = self.Perimeter.to_ref()
        data_dict["Structure"] = self.Structure.to_ref()
        data_dict["Windows"] = self.Windows.to_ref()
        data_dict["Category"] = validators.string(self.Category, allow_empty=True)
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name
        data_dict["YearFrom"] = self.YearFrom
        data_dict["YearTo"] = self.YearTo
        data_dict["Country"] = self.Country
        data_dict["ClimateZone"] = self.ClimateZone
        data_dict["Authors"] = self.Authors
        data_dict["AuthorEmails"] = self.AuthorEmails
        data_dict["Version"] = self.Version

        return data_dict

    def validate(self):
        """Validate object and fill in missing values."""
        return self

    def get_unique(self):
        """Replace recursively every objects with the first equivalent object."""

        def recursive_replace(umibase):
            for key, obj in umibase.mapping().items():
                if isinstance(
                    obj, (UmiBase, MaterialLayer, YearSchedulePart, MassRatio)
                ):
                    recursive_replace(obj)
                    setattr(umibase, key, obj.get_unique())
                elif isinstance(obj, list):
                    [
                        recursive_replace(obj)
                        for obj in obj
                        if isinstance(
                            obj, (UmiBase, MaterialLayer, YearSchedulePart, MassRatio)
                        )
                    ]

        recursive_replace(self)
        return self

    def mapping(self, validate=True):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return dict(
            Core=self.Core,
            Lifespan=self.Lifespan,
            PartitionRatio=self.PartitionRatio,
            Perimeter=self.Perimeter,
            Structure=self.Structure,
            Windows=self.Windows,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
            YearFrom=self.YearFrom,
            YearTo=self.YearTo,
            Country=self.Country,
            ClimateZone=self.ClimateZone,
            Authors=self.Authors,
            AuthorEmails=self.AuthorEmails,
            Version=self.Version,
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
                    for value in BuildingTemplate.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )

    def __hash__(self):
        """Return the hash value of self."""
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, BuildingTemplate):
            return NotImplemented
        else:
            return all(
                [
                    self.Core == other.Core,
                    self.Perimeter == other.Perimeter,
                    self.Structure == other.Structure,
                    self.Windows == other.Windows,
                    self.Lifespan == other.Lifespan,
                    self.PartitionRatio == other.PartitionRatio,
                    self.DefaultWindowToWallRatio == other.DefaultWindowToWallRatio,
                    self.YearFrom == other.YearFrom,
                    self.YearTo == other.YearTo,
                    self.Country == other.Country,
                    self.ClimateZone == other.ClimateZone,
                    self.Authors == other.Authors,
                    self.AuthorEmails == other.AuthorEmails,
                    self.Version == other.Version,
                ]
            )
