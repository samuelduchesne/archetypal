import pytest

from archetypal import IDF
from archetypal.zone_graph import ZoneGraph


class TestZoneGraph:
    """Series of tests for the :class:`ZoneGraph` class"""

    @pytest.fixture(scope="class")
    def small_office(config):
        file = (
            "tests/input_data/necb/NECB 2011-SmallOffice-NECB HDD "
            "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf"
        )
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = IDF(file, epw=w)
        yield idf

    def test_traverse_graph(self, small_office):
        """
        Args:
            small_office:
        """

        idf = small_office

        G = ZoneGraph.from_idf(idf, log_adj_report=False)

        assert G

    @pytest.fixture(scope="class")
    def G(self, config, small_office):
        """
        Args:
            config:
            small_office:
        """

        idf = small_office
        yield ZoneGraph.from_idf(idf)

    @pytest.mark.parametrize("adj_report", [True, False])
    def test_graph(self, small_office, adj_report):
        """Test the creation of a BuildingTemplate zone graph. Parametrize the
        creation of the adjacency report

        Args:
            small_office:
            adj_report:
        """
        import networkx as nx

        idf = small_office

        G1 = ZoneGraph.from_idf(idf, log_adj_report=adj_report)
        assert not nx.is_empty(G1)
        from eppy.bunch_subclass import EpBunch

        assert isinstance(
            G1.nodes["Sp-Attic Sys-0 Flr-2 Sch-- undefined - HPlcmt-core ZN"][
                "epbunch"
            ],
            EpBunch,
        )

    def test_graph_info(self, G):
        """test the info method on a ZoneGraph

        Args:
            G:
        """
        G.info()

    def test_viewgraph2d(self, G):
        """test the visualization of the zonegraph in 2d

        Args:
            G:
        """
        import networkx as nx

        G.plot_graph2d(
            nx.layout.circular_layout,
            (1),
            font_color="w",
            legend=True,
            font_size=8,
            color_nodes="core",
            node_labels_to_integers=True,
            plt_style="seaborn",
            save=False,
            show=False,
            filename="test",
        )

    @pytest.mark.parametrize("annotate", [True, "Name", ("core", None)])
    def test_viewgraph3d(self, G, annotate):
        """test the visualization of the zonegraph in 3d

        Args:
            G:
            annotate:
        """
        G.plot_graph3d(
            annotate=annotate,
            axis_off=True,
            save=False,
            show=False,
        )

    def test_core_graph(self, G):
        """
        Args:
            G:
        """
        H = G.core_graph

        assert len(H) == 1  # assert G has no nodes since Warehouse does not have a
        # core zone

    def test_perim_graph(self, G):
        """
        Args:
            G:
        """
        H = G.perim_graph

        assert len(H) > 0  # assert G has at least one node
