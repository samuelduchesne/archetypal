################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import logging as lg
import time
from copy import copy
from itertools import chain, repeat

import networkx
from deprecation import deprecated
from path import Path
from sigfig import round
from tqdm import tqdm

import archetypal
from archetypal import log
from archetypal.template import (
    DomesticHotWaterSetting,
    MassRatio,
    MaterialLayer,
    StructureInformation,
    UmiBase,
    WindowSetting,
    YearSchedulePart,
    ZoneDefinition,
)
from archetypal.utils import reduce


class BuildingTemplate(UmiBase):
    """Main class supporting the definition of a single building template.

    .. image:: ../images/template/buildingtemplate.png
    """

    def __init__(
        self,
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
        super(BuildingTemplate, self).__init__(**kwargs)
        self._zone_graph = None
        self._partition_ratio = PartitionRatio
        self.Lifespan = Lifespan
        self.Core = Core
        self.Perimeter = Perimeter
        self.Structure = Structure
        self.Windows = Windows
        self.DefaultWindowToWallRatio = DefaultWindowToWallRatio
        self.YearFrom = YearFrom
        self.YearTo = YearTo
        self.Country = Country if Country else []
        self.ClimateZone = ClimateZone if ClimateZone else []
        self.Authors = Authors if Authors else []
        self.AuthorEmails = AuthorEmails if AuthorEmails else []
        self.Version = Version

        self._allzones = []

    @property
    def PartitionRatio(self):
        if self._partition_ratio is None:
            self._partition_ratio = self.idf.partition_ratio
        return self._partition_ratio

    def __hash__(self):
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __eq__(self, other):
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

    @classmethod
    @deprecated(
        deprecated_in="1.3.1",
        removed_in="1.5",
        current_version=archetypal.__version__,
        details="Use from_dict function instead",
    )
    def from_json(cls, *args, **kwargs):

        return cls.from_dict(*args, **kwargs)

    @classmethod
    def from_dict(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        bt = cls(*args, **kwargs)

        ref = kwargs.get("Core", None)
        bt.Core = bt.get_ref(ref)
        ref = kwargs.get("Perimeter", None)
        bt.Perimeter = bt.get_ref(ref)
        ref = kwargs.get("Structure", None)
        bt.Structure = bt.get_ref(ref)
        ref = kwargs.get("Windows", None)
        try:
            idf = kwargs.get("idf", None)
            bt.Windows = WindowSetting.from_dict(Name=ref.pop("Name"), **ref, idf=idf)
        except:
            bt.Windows = bt.get_ref(ref)

        return bt

    @classmethod
    def from_idf(cls, idf, **kwargs):
        """Create a BuildingTemplate from an IDF object.

        Args:
            idf (IDF):
            **kwargs:
        """
        # initialize empty BuildingTemplate
        name = kwargs.pop("Name", Path(idf.idfname).basename().splitext()[0])
        bt = cls(Name=name, idf=idf, **kwargs)

        epbunch_zones = idf.idfobjects["ZONE"]
        zones = [
            ZoneDefinition.from_zone_epbunch(ep_zone, allow_duplicates=True, **kwargs)
            for ep_zone in tqdm(epbunch_zones, desc=f"Creating UMI objects for {name}")
        ]

        zone: ZoneDefinition
        bt.cores = list(
            chain.from_iterable(
                [
                    list(repeat(copy(zone), zone.multiplier))
                    for zone in zones
                    if zone.is_core
                ]
            )
        )
        bt.perims = list(
            chain.from_iterable(
                [
                    list(repeat(copy(zone), zone.multiplier))
                    for zone in zones
                    if not zone.is_core
                ]
            )
        )
        # do Core and Perim zone reduction
        bt.reduce(bt.cores, bt.perims)

        # resolve StructureInformation and WindowSetting
        bt.Structure = StructureInformation(
            Name=bt.Name + "_StructureDefinition",
            MassRatios=[MassRatio.generic()],
            idf=idf,
        )
        bt.Windows = bt.Perimeter.Windows

        bt.Comments += "\n".join(
            [
                "WWR calculated for original model: ",
                bt.idf.wwr().to_string(),
                "where East=90, South=180, West=270, North=0\n",
            ]
        )

        return bt

    def reduce(self, cores, perims):
        """Reduce the building to its simplest core and perimeter zones."""
        log("Initiating complexity reduction...")
        start_time = time.time()

        # reduce list of core zones
        if cores:
            self.Core = reduce(
                ZoneDefinition.combine,
                tqdm(
                    cores,
                    desc=f"Reducing core zones {self.idf.position}-{self.idf.name}",
                ),
            )
            self.Core.Name = f"{self.Name}_ZoneDefinition_Core"  # set name

        # reduce list of perimeter zones
        if not perims:
            raise ValueError(
                "Building complexity reduction must have at least one perimeter zone"
            )
        else:
            try:
                self.Perimeter = reduce(
                    ZoneDefinition.combine,
                    tqdm(
                        perims,
                        desc=f"Reducing perimeter zones {self.idf.position}-{self.idf.name}",
                    ),
                )
                self.Perimeter.Name = f"{self.Name}_ZoneDefinition_Perimeter"
            except Exception as e:
                raise e

        # If all perimeter zones, assign self.Perimeter to core.
        if not self.Core:
            self.Core = self.Perimeter
            self.Core.Name = f"{self.Name}_ZoneDefinition"  # rename as both core/perim

        # assign generic window if None
        if self.Perimeter.Windows is None:
            # create generic window
            self.Perimeter.Windows = WindowSetting.generic(
                idf=self.idf, Name="Generic Window"
            )

        if not self.Core.DomesticHotWater or not self.Perimeter.DomesticHotWater:
            dhw = DomesticHotWaterSetting.whole_building(self.idf)
            if not self.Core.DomesticHotWater:
                self.Core.DomesticHotWater = dhw
            if not self.Perimeter.DomesticHotWater:
                self.Perimeter.DomesticHotWater = dhw

        log(
            f"Equivalent core zone has an area of {self.Core.area:,.0f} m2",
            level=lg.DEBUG,
        )
        log(
            f"Equivalent perimeter zone has an area of {self.Perimeter.area:,.0f} m2",
            level=lg.DEBUG,
        )
        log(
            f"Completed model complexity reduction for BuildingTemplate '{self.Name}' "
            f"in {time.time() - start_time:,.2f}"
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

    def to_json(self):
        """Convert class properties to dict"""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["Core"] = self.Core.to_dict()
        data_dict["Lifespan"] = self.Lifespan
        data_dict["PartitionRatio"] = round(self.PartitionRatio, 2)
        data_dict["Perimeter"] = self.Perimeter.to_dict()
        data_dict["Structure"] = self.Structure.to_dict()
        data_dict["Windows"] = self.Windows.to_dict()
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
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
        """Recursively replaces every UmiBase objects with the first instance
        satisfying equality"""

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

    def mapping(self):
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


