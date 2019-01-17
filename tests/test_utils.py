from shapely.geometry import Polygon

from archetypal import project_geom


def test_projection():
    poly = Polygon(((-73.580147, 45.509472), (-73.551007, 45.509472),
                    (-73.551007, 45.488723), (-73.580147, 45.488723),
                    (-73.580147, 45.509472)))
    crs = {'init': 'epsg:4326'}
    to_crs = {'init': 'epsg:2950'}
    lat_lon = {'init': 'epsg:4326'}
    po1 = project_geom(poly, from_crs=crs, to_crs=to_crs, to_latlon=False)
    po2 = project_geom(poly, from_crs=crs, to_crs=None, to_latlon=False)
    po3 = project_geom(poly, from_crs=crs, to_crs=None, to_latlon=True)
    po4 = project_geom(poly, from_crs=crs, to_crs=lat_lon, to_latlon=False)
    # po3 and po4 should be equal since they both are projected lat-lon
    assert po3 == po4

