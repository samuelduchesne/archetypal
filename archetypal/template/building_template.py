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

import networkx
import tabulate
from eppy.bunch_subclass import BadEPFieldError
from tqdm import tqdm

from archetypal import log, save_and_show
from archetypal.template import UmiBase, Unique, ZoneGraph, Zone, \
    resolve_obco, WindowSetting, StructureDefinition, MassRatio


class BuildingTemplate(UmiBase, metaclass=Unique):
    """Main class supporting the definition of a single building template.

    .. image:: ../images/template/buildingtemplate.png

    """

    def __init__(self, Core=None,
                 Perimeter=None,
                 Structure=None,
                 Windows=None,
                 Lifespan=60,
                 PartitionRatio=0.35,
                 **kwargs):
        """Initialize a :class:`BuildingTemplate` object with the following
        attributes:

        Args:
            Core (Zone): The Zone object defining the core zone. see
                :class:`Zone` for more details.
            Perimeter (Zone): The Zone object defining the perimeter zone. see
                :class:`Zone` for more details.
            Structure (StructureDefinition): The StructureDefinition object
                defining the structural properties of the template.
            Windows (WindowSetting): The WindowSetting object defining the
                window properties of the object.
            Lifespan (float): The projected lifespan of the building template in
                years. Used in various calculations such as embodied energy.
            PartitionRatio (float): The ratio of partition wall to floor area.
            **kwargs: other optional keywords passed to other constructors.
        """
        super(BuildingTemplate, self).__init__(**kwargs)
        self._zone_graph = None
        self.PartitionRatio = PartitionRatio
        self.Lifespan = Lifespan
        self.Core = Core
        self.Perimeter = Perimeter
        self.Structure = Structure
        self.Windows = Windows

    def zone_graph(self, log_adj_report=True, skeleton=False, force=False):
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
        if self._zone_graph and force is False:
            return self._zone_graph

        start_time = time.time()
        idf = self.idf

        G = ZoneGraph(name=idf.name)

        def is_core(this_zone):
            # if all surfaces don't have boundary condition == "Outdoors"
            iscore = True
            for s in this_zone.zonesurfaces:
                try:
                    if int(s.tilt) == 90:
                        obc = s.Outside_Boundary_Condition.lower()
                        if obc == 'outdoors' or obc == 'foundation' or obc == \
                                'ground':
                            iscore = False
                            break
                except BadEPFieldError:
                    pass  # pass surfaces that don't have an OBC,
                    # eg. InternalMass
            return iscore

        counter = 0
        for zone in tqdm(idf.idfobjects['ZONE'], desc='zone_loop'):
            # initialize the adjacency report dictionary. default list.
            adj_report = defaultdict(list)
            zone_obj = None
            if not skeleton:
                zone_obj = Zone.from_zone_epbunch(zone, sql=self.sql)
                zonesurfaces = zone_obj._zonesurfaces
            else:
                zonesurfaces = zone.zonesurfaces
            G.add_node(zone.Name, epbunch=zone, core=is_core(zone),
                       zone=zone_obj)

            for surface in zonesurfaces:
                if surface.key.upper() == 'INTERNALMASS':
                    # Todo deal with internal mass surfaces
                    pass
                else:
                    adj_surf, adj_zone = resolve_obco(surface)

                    if adj_zone and adj_surf:
                        counter += 1

                        if skeleton:
                            zone_obj = None
                        else:
                            zone_obj = Zone.from_zone_epbunch(adj_zone,
                                                              sql=self.sql)

                        # create node for adjacent zone
                        G.add_node(adj_zone.Name,
                                   epbunch=adj_zone,
                                   core=is_core(adj_zone),
                                   zone=zone_obj)
                        try:
                            this_cstr = surface[
                                'Construction_Name']
                            their_cstr = adj_surf[
                                'Construction_Name']
                            is_diff_cstr = surface['Construction_Name'] \
                                           != adj_surf['Construction_Name']
                        except:
                            this_cstr, their_cstr, is_diff_cstr = None, \
                                                                  None, None
                        # create edge from this zone to the adjacent zone
                        G.add_edge(zone.Name, adj_zone.Name,
                                   this_cstr=this_cstr,
                                   their_cstr=their_cstr,
                                   is_diff_cstr=is_diff_cstr)

                        add_to_report(adj_report, zone, surface, adj_zone,
                                      adj_surf,
                                      counter)
                    else:
                        pass
            if log_adj_report:
                msg = 'Printing Adjacency Report for zone %s\n' % zone.Name
                msg += tabulate.tabulate(adj_report, headers='keys')
                log(msg)

        log("Created zone graph in {:,.2f} seconds".format(
            time.time() - start_time))
        log(networkx.info(G), lg.DEBUG)
        self._zone_graph = G
        return self._zone_graph

    def view_building(self, fig_height=None, fig_width=6, plot_graph=False,
                      save=False, show=True, close=False, ax=None,
                      axis_off=False, cmap='plasma', dpi=300, file_format='png',
                      azim=-60, elev=30, filename=None, opacity=0.5,
                      proj_type='persp', **kwargs):
        """
        Args:
            fig_height (float): matplotlib figure height in inches.
            fig_width (float): matplotlib figure width in inches.
            plot_graph (bool): if True, add the graph plot to this plot.
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
            filename (str): the name of the file if saving.
            opacity (float): 0.0 transparent through 1.0 opaque
            proj_type (str): Type of projection, accepts 'persp' and 'ortho'.
            **kwargs:
        """
        from geomeppy.view_geometry import _get_collections, _get_limits
        from mpl_toolkits.mplot3d import Axes3D
        import matplotlib.pyplot as plt

        if fig_height is None:
            fig_height = fig_width

        if ax:
            fig = plt.gcf()
        else:
            fig = plt.figure(figsize=(fig_width, fig_height), dpi=dpi)
            ax = Axes3D(fig)

        collections = _get_collections(self.idf, opacity=opacity)
        for c in collections:
            ax.add_collection3d(c)

        # Set the initial view
        ax.view_init(elev, azim)
        ax.set_proj_type(proj_type)

        # calculate and set the axis limits
        limits = _get_limits(idf=self.idf)
        ax.set_xlim(limits["x"])
        ax.set_ylim(limits["y"])
        ax.set_zlim(limits["z"])

        if plot_graph:
            annotate = kwargs.get('annotate', False)
            self.zone_graph(log_adj_report=False, force=False).plot_graph3d(
                ax=ax, annotate=annotate)

        fig, ax = save_and_show(fig=fig, ax=ax, save=save, show=show,
                                close=close, filename=filename,
                                file_format=file_format, dpi=dpi,
                                axis_off=axis_off, extent=None)
        return fig, ax

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        bt = cls(*args, **kwargs)

        ref = kwargs.get('Core', None)
        bt.Core = bt.get_ref(ref)
        ref = kwargs.get('Perimeter', None)
        bt.Perimeter = bt.get_ref(ref)
        ref = kwargs.get('Structure', None)
        bt.Structure = bt.get_ref(ref)
        ref = kwargs.get('Windows', None)
        try:
            bt.Windows = WindowSetting.from_json(Name=ref.pop('Name'), **ref)
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
        name = kwargs.pop('Name', idf.idfobjects['BUILDING'][0].Name)
        bt = cls(Name=name, idf=idf, **kwargs)

        # do Core and Perim zone reduction
        bt.reduce()

        # resolve StructureDefinition and WindowSetting
        bt.Structure = StructureDefinition(
            Name=bt.Name + '_StructureDefinition', MassRatios=[
                MassRatio.generic()], idf=idf)
        bt.Windows = bt.Perimeter.Windows

        return bt

    def reduce(self, **zone_graph_kwargs):
        """Reduce the building to its simplest core and perimeter zones."""

        # Determine if core graph is not empty
        core_graph = self.zone_graph(**zone_graph_kwargs).core_graph
        perim_graph = self.zone_graph(**zone_graph_kwargs).perim_graph

        self.Core = self._graph_reduce(core_graph)
        self.Perimeter = self._graph_reduce(perim_graph)

        if self.Perimeter.Windows is None:
            # create generic window
            self.Perimeter.Windows = WindowSetting.generic(idf=self.idf)

        if not self.Core:
            self.Core = self.Perimeter

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
            Zone: The reduced zone
        """
        if len(G) < 1:
            log('No zones for building graph %s' % G.name)
            return None
        else:
            log('starting reduce process for building %s' % self.Name)
            start_time = time.time()

            # start from the highest degree node
            subgraphs = sorted(networkx.connected_component_subgraphs(G),
                               key=len, reverse=True)
            from functools import reduce
            from operator import add
            bundle_zone = reduce(add,
                                 [zone for subG in subgraphs for name, zone in
                                  subG.nodes(data='zone')])

            log('completed zone reduction for building {} in'
                '{:,.2f} seconds'.format(self.Name, time.time() - start_time))
            return bundle_zone

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["Core"] = self.Core.to_dict()
        data_dict["Lifespan"] = self.Lifespan
        data_dict["PartitionRatio"] = self.PartitionRatio
        data_dict["Perimeter"] = self.Perimeter.to_dict()
        data_dict["Structure"] = self.Structure.to_dict()
        data_dict["Windows"] = self.Windows.to_dict()
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict


def add_to_report(adj_report, zone, surface, adj_zone, adj_surf, counter):
    """
    Args:
        adj_report (dict): the report dict to append to.
        zone (EpBunch):
        surface (EpBunch):
        adj_zone (EpBunch):
        adj_surf:
        counter (int): Counter.
    """
    adj_report['#'].append(counter)
    adj_report['Zone Name'].append(zone.Name)
    adj_report['Surface Type'].append(surface['Surface_Type'])
    adj_report['Adjacent Zone'].append(adj_zone['Name'])
    adj_report['Surface Type_'].append(adj_surf['Surface_Type'])
