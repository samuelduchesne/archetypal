################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import logging as lg
import time
from collections import defaultdict
from copy import copy
from itertools import chain, repeat

import matplotlib.collections
import matplotlib.colors
import networkx
import tabulate
from deprecation import deprecated
from eppy.bunch_subclass import EpBunch
from path import Path
from sigfig import round
from tqdm import tqdm

import archetypal
from archetypal import log, save_and_show
from archetypal.template import (
    MassRatio,
    MaterialLayer,
    StructureInformation,
    UmiBase,
    WindowSetting,
    YearSchedulePart,
    ZoneDefinition,
    is_core,
    resolve_obco,
    DomesticHotWaterSetting,
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
            G (ZoneGraph):

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


def add_to_report(adj_report, zone, surface, adj_zone, adj_surf, counter):
    """
    Args:
        adj_report (dict): the report dict to append to.
        zone (EpBunch):
        surface (EpBunch):
        adj_zone (EpBunch):
        adj_surf (EpBunch):
        counter (int): Counter.
    """
    adj_report["#"].append(counter)
    adj_report["Zone Name"].append(zone.Name)
    adj_report["Surface Type"].append(surface["Surface_Type"])
    adj_report["Adjacent Zone"].append(adj_zone["Name"])
    adj_report["Surface Type_"].append(adj_surf["Surface_Type"])


class ZoneGraph(networkx.Graph):
    """A subclass of :class:`networkx.Graph`. This class implements useful
    methods to visualize and navigate a template along the thermal adjacency of
    its zones.

    There are currently two methods to visualize the graph:

    - :func:`plot in 3d <plot_graph3d>` to get a 3-dimensional view of the
      building.
    - :func:`plot in 2d <plot_graph2d>` to get a 2-dimensional view of the
      building zones

    Note:
        A Graph stores nodes and edges with optional data, or attributes.

        Graphs hold undirected edges. Self loops are allowed but multiple
        (parallel) edges are not.

        Nodes can be arbitrary (hashable) Python objects with optional key/value
        attributes. By convention `None` is not used as a node.

        Edges are represented as links between nodes with optional key/value
        attributes.
    """

    @classmethod
    def from_idf(cls, idf, log_adj_report=True, **kwargs):
        """Create a graph representation of all the building zones. An edge
        between two zones represents the adjacency of the two zones.

        If skeleton is False, this method will create all the building
        objects iteratively over the building zones.

        Args:
            log_adj_report (bool, optional): If True, prints an adjacency report
                in the log.
            skeleton (bool, optional): If True, create a zone graph without
                creating hierarchical objects, eg. zones > zoneloads > ect.
            force (bool): If True, will recalculate the graph.

        Returns:
            ZoneGraph: The building's zone graph object
        """

        start_time = time.time()

        G = cls(name=idf.name)

        counter = 0
        zone: EpBunch
        for zone in tqdm(
            idf.idfobjects["ZONE"], desc="zone_loop", position=idf.position, **kwargs
        ):
            # initialize the adjacency report dictionary. default list.
            adj_report = defaultdict(list)
            zone_obj = None
            zonesurfaces = zone.zonesurfaces
            _is_core = is_core(zone)
            G.add_node(zone.Name, epbunch=zone, core=_is_core, zone=zone_obj)

            for surface in zonesurfaces:
                if surface.key.upper() in ["INTERNALMASS", "WINDOWSHADINGCONTROL"]:
                    # Todo deal with internal mass surfaces
                    pass
                else:
                    adj_zone: EpBunch
                    adj_surf: EpBunch
                    adj_surf, adj_zone = resolve_obco(surface)

                    if adj_zone and adj_surf:
                        counter += 1

                        zone_obj = None
                        _is_core = is_core(zone)

                        # create node for adjacent zone
                        G.add_node(
                            zone.Name, epbunch=adj_zone, core=_is_core, zone=zone_obj
                        )
                        try:
                            this_cstr = surface["Construction_Name"]
                            their_cstr = adj_surf["Construction_Name"]
                            is_diff_cstr = (
                                surface["Construction_Name"]
                                != adj_surf["Construction_Name"]
                            )
                        except:
                            this_cstr, their_cstr, is_diff_cstr = None, None, None
                        # create edge from this zone to the adjacent zone
                        G.add_edge(
                            zone.Name,
                            adj_zone.Name,
                            this_cstr=this_cstr,
                            their_cstr=their_cstr,
                            is_diff_cstr=is_diff_cstr,
                        )

                        add_to_report(
                            adj_report, zone, surface, adj_zone, adj_surf, counter
                        )
                    else:
                        pass
            if log_adj_report:
                msg = "Printing Adjacency Report for zone %s\n" % zone.Name
                msg += tabulate.tabulate(adj_report, headers="keys")
                log(msg)

        log("Created zone graph in {:,.2f} seconds".format(time.time() - start_time))
        log(networkx.info(G), lg.DEBUG)
        return G

    def __init__(self, incoming_graph_data=None, **attr):
        """Initialize a graph with edges, name, or graph attributes.

        Wrapper around the :class:`networkx.Graph` class.

        Args:
            incoming_graph_data: input graph (optional, default: None) Data to
                initialize graph. If None (default) an empty graph is created.
                The data can be an edge list, or any NetworkX graph object. If
                the corresponding optional Python packages are installed the
                data can also be a NumPy matrix or 2d ndarray, a SciPy sparse
                matrix, or a PyGraphviz graph.
            attr: keyword arguments, optional (default= no attributes)
                Attributes to add to graph as key=value pairs.
        """
        super(ZoneGraph, self).__init__(incoming_graph_data=incoming_graph_data, **attr)

    def plot_graph3d(
        self,
        fig_height=None,
        fig_width=6,
        save=False,
        show=True,
        close=False,
        ax=None,
        axis_off=False,
        cmap="plasma",
        dpi=300,
        file_format="png",
        azim=-60,
        elev=30,
        proj_type="persp",
        filename=None,
        annotate=False,
        plt_style="ggplot",
    ):
        """Plot the :class:`archetypal.template.ZoneGraph` in a 3D plot.

        The size of the node is relative to its
        :func:`networkx.Graph.degree`. The node degree is the number of edges
        adjacent to the node.

        The nodes are positioned in 3d space according to the mean value of
        the surfaces centroids. For concave volumes, this corresponds to the
        center of gravity of the volume. Some weird positioning can occur for
        convex volumes.

        Todo:
            Create an Example

        Args:
            fig_height (float): matplotlib figure height in inches.
            fig_width (float): matplotlib figure width in inches.
            save (bool): if True, save the figure as an image file to disk.
            show (bool): if True, show the figure.
            close (bool): close the figure (only if show equals False) to
                prevent display.
            ax (matplotlib.axes._axes.Axes, optional): An existing axes object
                on which to plot this graph.
            axis_off (bool): If True, turn off the matplotlib axis.
            cmap (str): The name a registered
                :class:`matplotlib.colors.Colormap`.
            dpi (int): the resolution of the image file if saving.
            file_format (str): the format of the file to save (e.g., 'jpg',
                'png', 'svg', 'pdf')
            azim (float): Azimuthal viewing angle, defaults to -60.
            elev (float): Elevation viewing angle, defaults to 30.
            proj_type (str): Type of projection, accepts 'persp' and 'ortho'.
            filename (str): the name of the file if saving.
            annotate (bool or str or tuple): If True, annotates the node with
                the Zone Name. Pass an EpBunch *field_name* to retrieve data
                from the zone EpBunch. Pass a tuple (data, key) to retrieve data
                from the graph: eg. ('core', None) will retrieve the attribute
                'core' associated to the node. The second tuple element serves
                as a key on the first: G.nodes(data=data)[key].
            plt_style (str, dict, or list): A style specification. Valid options
                are: - str: The name of a style or a path/URL to a style file.
                For a list of available style names, see `style.available` . -
                dict: Dictionary with valid key/value pairs for
                :attr:`matplotlib.rcParams`. - list: A list of style specifiers
                (str or dict) applied from first to last in the list.

        Returns:
            fig, ax: fig, ax
        """
        import matplotlib.pyplot as plt
        import numpy as np
        from mpl_toolkits.mplot3d import Axes3D

        def avg(zone: EpBunch):
            """calculate the zone centroid coordinates"""
            x_, y_, z_, dem = 0, 0, 0, 0
            from geomeppy.geom.polygons import Polygon3D, Vector3D
            from geomeppy.recipes import translate_coords

            ggr = zone.theidf.idfobjects["GLOBALGEOMETRYRULES"][0]

            for surface in zone.zonesurfaces:
                if surface.key.upper() in ["INTERNALMASS", "WINDOWSHADINGCONTROL"]:
                    pass
                else:
                    dem += 1  # Counter for average calc at return
                    if ggr.Coordinate_System.lower() == "relative":
                        # add zone origin to surface coordinates and create
                        # Polygon3D from updated coords.
                        zone = zone.theidf.getobject("ZONE", surface.Zone_Name)
                        poly3d = Polygon3D(surface.coords)
                        origin = (zone.X_Origin, zone.Y_Origin, zone.Z_Origin)
                        coords = translate_coords(poly3d, Vector3D(*origin))
                        poly3d = Polygon3D(coords)
                    else:
                        # Polygon3D from surface coords
                        poly3d = Polygon3D(surface.coords)
                    x, y, z = poly3d.centroid
                    x_ += x
                    y_ += y
                    z_ += z
            return x_ / dem, y_ / dem, z_ / dem

        # Get node positions in a dictionary
        pos = {name: avg(epbunch) for name, epbunch in self.nodes(data="epbunch")}

        # Get the maximum number of edges adjacent to a single node
        edge_max = max(1, max([self.degree[i] for i in self.nodes]))  # min = 1

        # Define color range proportional to number of edges adjacent to a
        # single node
        colors = {
            i: plt.cm.get_cmap(cmap)(self.degree[i] / edge_max) for i in self.nodes
        }
        labels = {}
        if annotate:
            # annotate can be bool or str.
            if isinstance(annotate, bool):
                # if True, default to 'Name' field
                annotate = "Name"
            if isinstance(annotate, str):
                # create dict of the form {id: (x, y, z, label, zdir)}. zdir is
                # None by default.
                labels = {
                    name: (*pos[name], data[annotate], None)
                    for name, data in self.nodes(data="epbunch")
                }
            if isinstance(annotate, tuple):
                data, key = annotate
                if key:
                    labels = {
                        name: (*pos[name], data[key], None)
                        for name, data in self.nodes(data=data)
                    }
                else:
                    labels = {
                        name: (*pos[name], data, None)
                        for name, data in self.nodes(data=data)
                    }

        # 3D network plot
        with plt.style.context(plt_style):
            if fig_height is None:
                fig_height = fig_width

            if ax:
                fig = plt.gcf()
            else:
                fig = plt.figure(figsize=(fig_width, fig_height), dpi=dpi)
                ax = Axes3D(fig)

            # Loop on the pos dictionary to extract the x,y,z coordinates of
            # each node
            for key, value in pos.items():
                xi = value[0]
                yi = value[1]
                zi = value[2]

                # Scatter plot
                ax.scatter(
                    xi,
                    yi,
                    zi,
                    color=colors[key],
                    s=20 + 20 * self.degree[key],
                    edgecolors="k",
                    alpha=0.7,
                )
                if annotate:
                    # Add node label
                    ax.text(*labels[key], fontsize=4)
            # Loop on the list of edges to get the x,y,z, coordinates of the
            # connected nodes
            # Those two points are the extrema of the line to be plotted
            for i, j in enumerate(self.edges()):
                x = np.array((pos[j[0]][0], pos[j[1]][0]))
                y = np.array((pos[j[0]][1], pos[j[1]][1]))
                z = np.array((pos[j[0]][2], pos[j[1]][2]))

                # Plot the connecting lines
                ax.plot(x, y, z, c="black", alpha=0.5)

        # Set the initial view
        ax.view_init(elev, azim)
        ax.set_proj_type(proj_type)

        # Hide the axes
        if axis_off:
            ax.set_axis_off()

        if filename is None:
            filename = "unnamed"

        fig, ax = save_and_show(
            fig=fig,
            ax=ax,
            save=save,
            show=show,
            close=close,
            filename=filename,
            file_format=file_format,
            dpi=dpi,
            axis_off=axis_off,
            extent=None,
        )
        return fig, ax

    def plot_graph2d(
        self,
        layout_function,
        *func_args,
        color_nodes=None,
        fig_height=None,
        fig_width=6,
        node_labels_to_integers=False,
        legend=False,
        with_labels=True,
        arrows=True,
        save=False,
        show=True,
        close=False,
        ax=None,
        axis_off=False,
        cmap="plasma",
        dpi=300,
        file_format="png",
        filename="unnamed",
        plt_style="ggplot",
        extent="tight",
        **kwargs,
    ):
        """Plot the adjacency of the zones as a graph. Choose a layout from the
        :mod:`networkx.drawing.layout` module, the
        :mod:`Graphviz AGraph (dot)<networkx.drawing.nx_agraph>` module, the
        :mod:`Graphviz with pydot<networkx.drawing.nx_pydot>` module. Then, plot
        the graph using matplotlib using the :mod:`networkx.drawing.py_lab`

        Examples:
            >>> import networkx as nx
            >>> G = BuildingTemplate().from_idf
            >>> G.plot_graph2d(nx.nx_agraph.graphviz_layout, ('dot'),
            >>>                font_color='w', legend=True, font_size=8,
            >>>                color_nodes='core',
            >>>                node_labels_to_integers=True,
            >>>                plt_style='seaborn', save=True,
            >>>                filename='test')

        Args:
            layout_function (func): One of the networkx layout functions.
            *func_args: The layout function arguments as a tuple. The first
                argument (self) is already supplied.
            color_nodes (bool or str): False by default. If a string is passed
                the nodes are colored according to a data attribute of the
                graph. By default, the original node names is accessed with the
                'name' attribute.
            fig_height (float): matplotlib figure height in inches.
            fig_width (float): matplotlib figure width in inches.
            node_labels_to_integers:
            legend:
            with_labels (bool, optional): Set to True to draw labels on the
            arrows (bool, optional): If True, draw arrowheads. Note: Arrows will
                be the same color as edges.
            save (bool): if True, save the figure as an image file to disk.
            show (bool): if True, show the figure.
            close (bool): close the figure (only if show equals False) to
                prevent display.
            ax (matplotlib.axes._axes.Axes, optional): An existing axes object
                on which to plot this graph.
            axis_off (bool): If True, turn off the matplotlib axis.
            cmap (str): The name a registered
                :class:`matplotlib.colors.Colormap`.
            dpi (int): the resolution of the image file if saving.
            file_format (str): the format of the file to save (e.g., 'jpg',
                'png', 'svg', 'pdf')
            filename (str): the name of the file if saving.
            plt_style (str, dict, or list): A style specification. Valid options
                are: - str: The name of a style or a path/URL to a style file.
                For a list of available style names, see `style.available` . -
                dict: Dictionary with valid key/value pairs for
                :attr:`matplotlib.rcParams`. - list: A list of style specifiers
                (str or dict) applied from first to last in the list.
            extent:
            **kwargs: keywords passed to :func:`networkx.draw_networkx`

        Returns:
            (tuple): The fig and ax objects
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("Matplotlib required for draw()")
        except RuntimeError:
            log("Matplotlib unable to open display", lg.WARNING)
            raise
        G = self.copy()
        if node_labels_to_integers:
            G = networkx.convert_node_labels_to_integers(G, label_attribute="name")
        tree = networkx.dfs_tree(G)
        pos = layout_function(tree, *func_args)
        with plt.style.context((plt_style)):
            if ax:
                fig = plt.gcf()
            else:
                if fig_height is None:
                    fig_height = fig_width
                fig, ax = plt.subplots(1, figsize=(fig_width, fig_height), dpi=dpi)

            if isinstance(color_nodes, str):
                from itertools import count

                groups = set(networkx.get_node_attributes(G, color_nodes).values())
                mapping = dict(zip(sorted(groups), count()))
                colors = [mapping[G.nodes[n][color_nodes]] for n in tree.nodes]
                colors = [discrete_cmap(len(groups), cmap).colors[i] for i in colors]
            font_color = kwargs.pop("font_color", None)
            font_size = kwargs.pop("font_size", None)
            paths_ = []
            for nt in tree:
                # choose nodes and color for each iteration
                nlist = [nt]
                label = "%s: %s" % (nt, G.nodes(data="name")[nt])
                if color_nodes:
                    node_color = [colors[nt]]
                else:
                    node_color = "#1f78b4"
                # draw the graph
                sc = networkx.draw_networkx_nodes(
                    tree,
                    pos=pos,
                    nodelist=nlist,
                    ax=ax,
                    node_color=node_color,
                    label=label,
                    cmap=cmap,
                    node_size=kwargs.get("node_size", 300),
                    node_shape=kwargs.get("node_shape", "o"),
                    alpha=kwargs.get("alpha", None),
                    vmin=kwargs.get("vmin", None),
                    vmax=kwargs.get("vmax", None),
                    linewidths=kwargs.get("linewidths", None),
                    edgecolors=kwargs.get("linewidths", None),
                )
                paths_.extend(sc.get_paths())
            scatter = matplotlib.collections.PathCollection(paths_)
            networkx.draw_networkx_edges(tree, pos, ax=ax, arrows=arrows, **kwargs)
            if with_labels:
                networkx.draw_networkx_labels(
                    G,
                    pos,
                    font_color=font_color,
                    font_size=font_size,
                    **kwargs,
                )

            if legend:
                bbox = kwargs.get("bbox_to_anchor", (1, 1))
                legend1 = ax.legend(
                    title=color_nodes, bbox_to_anchor=bbox, markerscale=0.5
                )
                ax.add_artist(legend1)

            # clear axis
            ax.axis("off")

            fig, ax = save_and_show(
                fig=fig,
                ax=ax,
                save=save,
                show=show,
                close=close,
                filename=filename,
                file_format=file_format,
                dpi=dpi,
                axis_off=axis_off,
                extent=extent,
            )
            return fig, ax

    @property
    def core_graph(self):
        """Returns a copy of the ZoneGraph containing only core zones"""
        nodes = [i for i, data in self.nodes(data="core") if data]
        H = self.subgraph(nodes).copy()
        H.name = "Core_" + self.name
        return H

    @property
    def perim_graph(self):
        """Returns a copy of the ZoneGraph containing only perimeter zones"""
        nodes = [i for i, data in self.nodes(data="core") if not data]
        H = self.subgraph(nodes).copy()
        H.name = "Perim_" + self.name
        return H

    def info(self, node=None):
        """Print short summary of information for the graph or the node n.

        Args:
            node (any hashable): A node in the graph
        """
        return log(networkx.info(G=self, n=node))


def discrete_cmap(N, base_cmap=None):
    """Create an N-bin discrete colormap from the specified input map

    Args:
        N:
        base_cmap:
    """

    # Note that if base_cmap is a string or None, you can simply do
    #    return plt.cm.get_cmap(base_cmap, N)
    # The following works for string, None, or a colormap instance:
    import matplotlib.pyplot as plt
    from numpy.core.function_base import linspace

    base = plt.cm.get_cmap(base_cmap)
    color_list = base(linspace(0, 1, N))
    cmap_name = base.name + str(N)
    return matplotlib.colors.ListedColormap(color_list, cmap_name, N)
