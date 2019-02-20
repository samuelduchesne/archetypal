import archetypal as ar


def test_graph_from_shp():
    import networkx as nx
    file = './input_data/shapefiles/ccum_reseau.shp'
    G = ar.graph_from_shp(file, simplify=True, crs=dict(init='epsg:2950'))
    assert not nx.is_empty(G)
