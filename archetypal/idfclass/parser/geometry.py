"""
Geometry utilities for IDF models.

Provides coordinate handling and transformations without geomeppy dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .objects import IDFObject
    from .document import IDFDocument


@dataclass(frozen=True, slots=True)
class Vector3D:
    """
    Immutable 3D vector.

    Example:
        >>> v = Vector3D(1.0, 2.0, 3.0)
        >>> v2 = v + Vector3D(1, 0, 0)
        >>> print(v2)
        Vector3D(2.0, 2.0, 3.0)
    """

    x: float
    y: float
    z: float

    def __add__(self, other: "Vector3D") -> "Vector3D":
        return Vector3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vector3D") -> "Vector3D":
        return Vector3D(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vector3D":
        return Vector3D(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> "Vector3D":
        return self * scalar

    def __truediv__(self, scalar: float) -> "Vector3D":
        return Vector3D(self.x / scalar, self.y / scalar, self.z / scalar)

    def __neg__(self) -> "Vector3D":
        return Vector3D(-self.x, -self.y, -self.z)

    def dot(self, other: "Vector3D") -> float:
        """Dot product."""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vector3D") -> "Vector3D":
        """Cross product."""
        return Vector3D(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        """Vector magnitude."""
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def normalize(self) -> "Vector3D":
        """Return unit vector."""
        mag = self.length()
        if mag == 0:
            return Vector3D(0, 0, 0)
        return self / mag

    def rotate_z(self, angle_deg: float) -> "Vector3D":
        """Rotate around Z axis by angle in degrees."""
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        return Vector3D(
            self.x * cos_a - self.y * sin_a,
            self.x * sin_a + self.y * cos_a,
            self.z,
        )

    def as_tuple(self) -> tuple[float, float, float]:
        """Return as tuple."""
        return (self.x, self.y, self.z)

    @classmethod
    def from_tuple(cls, t: Sequence[float]) -> "Vector3D":
        """Create from tuple or list."""
        return cls(float(t[0]), float(t[1]), float(t[2]))

    @classmethod
    def origin(cls) -> "Vector3D":
        """Return origin vector."""
        return cls(0.0, 0.0, 0.0)


@dataclass
class Polygon3D:
    """
    3D polygon defined by vertices.

    Example:
        >>> vertices = [Vector3D(0, 0, 0), Vector3D(1, 0, 0), Vector3D(1, 1, 0), Vector3D(0, 1, 0)]
        >>> poly = Polygon3D(vertices)
        >>> print(poly.area)
        1.0
    """

    vertices: list[Vector3D]

    @property
    def num_vertices(self) -> int:
        """Number of vertices."""
        return len(self.vertices)

    @property
    def normal(self) -> Vector3D:
        """Surface normal vector."""
        if self.num_vertices < 3:
            return Vector3D(0, 0, 1)

        # Use Newell's method for robustness
        n = Vector3D(0, 0, 0)
        for i in range(self.num_vertices):
            v1 = self.vertices[i]
            v2 = self.vertices[(i + 1) % self.num_vertices]
            n = Vector3D(
                n.x + (v1.y - v2.y) * (v1.z + v2.z),
                n.y + (v1.z - v2.z) * (v1.x + v2.x),
                n.z + (v1.x - v2.x) * (v1.y + v2.y),
            )
        return n.normalize()

    @property
    def area(self) -> float:
        """Surface area using cross product method."""
        if self.num_vertices < 3:
            return 0.0

        # Triangulate and sum areas
        total = Vector3D(0, 0, 0)
        v0 = self.vertices[0]

        for i in range(1, self.num_vertices - 1):
            v1 = self.vertices[i]
            v2 = self.vertices[i + 1]
            edge1 = v1 - v0
            edge2 = v2 - v0
            cross = edge1.cross(edge2)
            total = total + cross

        return total.length() / 2.0

    @property
    def centroid(self) -> Vector3D:
        """Geometric center."""
        if not self.vertices:
            return Vector3D.origin()

        x = sum(v.x for v in self.vertices) / self.num_vertices
        y = sum(v.y for v in self.vertices) / self.num_vertices
        z = sum(v.z for v in self.vertices) / self.num_vertices
        return Vector3D(x, y, z)

    @property
    def is_horizontal(self) -> bool:
        """Check if polygon is horizontal (floor/ceiling)."""
        n = self.normal
        return abs(n.z) > 0.99

    @property
    def is_vertical(self) -> bool:
        """Check if polygon is vertical (wall)."""
        n = self.normal
        return abs(n.z) < 0.01

    def translate(self, offset: Vector3D) -> "Polygon3D":
        """Return translated polygon."""
        return Polygon3D([v + offset for v in self.vertices])

    def rotate_z(self, angle_deg: float, anchor: Vector3D | None = None) -> "Polygon3D":
        """Rotate around Z axis."""
        if anchor is None:
            anchor = self.centroid

        rotated = []
        for v in self.vertices:
            # Translate to anchor, rotate, translate back
            relative = v - anchor
            rotated_rel = relative.rotate_z(angle_deg)
            rotated.append(rotated_rel + anchor)

        return Polygon3D(rotated)

    def as_tuple_list(self) -> list[tuple[float, float, float]]:
        """Return vertices as list of tuples."""
        return [v.as_tuple() for v in self.vertices]

    @classmethod
    def from_tuples(cls, coords: Sequence[Sequence[float]]) -> "Polygon3D":
        """Create from sequence of coordinate tuples."""
        return cls([Vector3D.from_tuple(c) for c in coords])


def get_surface_coords(surface: "IDFObject") -> Polygon3D | None:
    """
    Extract coordinates from a surface object.

    Works with BuildingSurface:Detailed, FenestrationSurface:Detailed, etc.
    """
    vertices = []

    # Try to get number of vertices
    num_verts = getattr(surface, "number_of_vertices", None)
    if num_verts is None:
        # Count vertex fields
        i = 1
        while True:
            x = getattr(surface, f"vertex_{i}_x_coordinate", None)
            if x is None:
                break
            i += 1
        num_verts = i - 1

    if num_verts == 0:
        return None

    # Extract vertices
    for i in range(1, int(num_verts) + 1):
        x = getattr(surface, f"vertex_{i}_x_coordinate", None)
        y = getattr(surface, f"vertex_{i}_y_coordinate", None)
        z = getattr(surface, f"vertex_{i}_z_coordinate", None)

        if x is not None and y is not None and z is not None:
            vertices.append(Vector3D(float(x), float(y), float(z)))

    if len(vertices) < 3:
        return None

    return Polygon3D(vertices)


def set_surface_coords(surface: "IDFObject", polygon: Polygon3D) -> None:
    """
    Set coordinates on a surface object.

    Updates vertex fields and number_of_vertices.
    """
    # Set number of vertices
    surface.number_of_vertices = len(polygon.vertices)

    # Set vertex coordinates
    for i, vertex in enumerate(polygon.vertices, 1):
        setattr(surface, f"vertex_{i}_x_coordinate", vertex.x)
        setattr(surface, f"vertex_{i}_y_coordinate", vertex.y)
        setattr(surface, f"vertex_{i}_z_coordinate", vertex.z)


def get_zone_origin(zone: "IDFObject") -> Vector3D:
    """Get the origin point of a zone."""
    x = getattr(zone, "x_origin", 0) or 0
    y = getattr(zone, "y_origin", 0) or 0
    z = getattr(zone, "z_origin", 0) or 0
    return Vector3D(float(x), float(y), float(z))


def get_zone_rotation(zone: "IDFObject") -> float:
    """Get the rotation angle of a zone in degrees."""
    angle = getattr(zone, "direction_of_relative_north", 0)
    return float(angle) if angle else 0.0


def translate_to_world(doc: "IDFDocument") -> None:
    """
    Translate model from relative to world coordinates.

    Applies zone origins and rotations to surface coordinates.
    """
    # Check coordinate system
    geo_rules = doc["GlobalGeometryRules"]
    if geo_rules:
        rules = geo_rules.first()
        coord_system = getattr(rules, "coordinate_system", "World")
        if coord_system and coord_system.lower() == "world":
            return  # Already in world coordinates

    # Get building north axis
    building = doc["Building"]
    north_axis = 0.0
    if building:
        b = building.first()
        north_axis = float(getattr(b, "north_axis", 0) or 0)

    # Process each zone
    for zone in doc["Zone"]:
        zone_origin = get_zone_origin(zone)
        zone_rotation = get_zone_rotation(zone)
        total_rotation = north_axis + zone_rotation

        # Get surfaces in this zone
        zone_name = zone.name
        surfaces = list(doc.get_referencing(zone_name))

        for surface in surfaces:
            # Only process surfaces with coordinates
            coords = get_surface_coords(surface)
            if coords is None:
                continue

            # Apply rotation
            if total_rotation != 0:
                coords = coords.rotate_z(total_rotation)

            # Apply translation
            coords = coords.translate(zone_origin)

            # Update surface
            set_surface_coords(surface, coords)

    # Update zone origins to zero
    for zone in doc["Zone"]:
        zone.x_origin = 0.0
        zone.y_origin = 0.0
        zone.z_origin = 0.0
        zone.direction_of_relative_north = 0.0

    # Update building north axis
    if building:
        b = building.first()
        b.north_axis = 0.0

    # Update coordinate system to World
    if geo_rules:
        rules = geo_rules.first()
        rules.coordinate_system = "World"


def calculate_surface_area(surface: "IDFObject") -> float:
    """Calculate the area of a surface."""
    coords = get_surface_coords(surface)
    return coords.area if coords else 0.0


def calculate_zone_floor_area(doc: "IDFDocument", zone_name: str) -> float:
    """Calculate the total floor area of a zone."""
    total_area = 0.0

    for surface in doc["BuildingSurface:Detailed"]:
        if getattr(surface, "zone_name", "").upper() != zone_name.upper():
            continue

        surface_type = getattr(surface, "surface_type", "")
        if surface_type and surface_type.lower() == "floor":
            total_area += calculate_surface_area(surface)

    return total_area


def calculate_zone_volume(doc: "IDFDocument", zone_name: str) -> float:
    """
    Calculate the volume of a zone from its surfaces.

    Uses the divergence theorem to compute volume from surface polygons.
    """
    volume = 0.0

    for surface in doc["BuildingSurface:Detailed"]:
        if getattr(surface, "zone_name", "").upper() != zone_name.upper():
            continue

        coords = get_surface_coords(surface)
        if coords is None or coords.num_vertices < 3:
            continue

        # Contribution to volume using signed volume of tetrahedra
        centroid = coords.centroid
        for i in range(coords.num_vertices):
            v1 = coords.vertices[i]
            v2 = coords.vertices[(i + 1) % coords.num_vertices]

            # Volume of tetrahedron with origin
            volume += v1.dot(v2.cross(centroid)) / 6.0

    return abs(volume)
