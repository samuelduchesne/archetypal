"""#Enter module description here.

Created on 2022-07-08

@author: samuel.letellier-duc 
"""

import logging
import sys
from enum import Enum
from typing import Optional

from pint import Quantity
from pydantic import BaseModel, PositiveFloat, Extra, validator, root_validator

from archetypal.settings import unit_registry

logger = logging.getLogger(__name__)
# use logger instead of print


class Direction(float, Enum):
    NORTH = 1
    NORTH_NORTH_EAST = 1.25
    NORTH_EAST = 1.5
    EAST_NORTH_EAST = 1.75
    EAST = 2
    EAST_SOUTH_EAST = 2.25
    SOUTH_EAST = 2.5
    SOUTH_SOUTH_EAST = 2.75
    SOUTH = 3
    SOUTH_SOUTH_WEST = 3.25
    SOUTH_WEST = 3.5
    WEST_SOUTH_WEST = 3.75
    WEST = 4
    WEST_NORTH_WEST = 0.75
    NORTH_WEST = 0.5
    NORTH_NORTH_WEST = 0.25

    def angle(self):
        right_angle = 90.0
        return right_angle * (self.value - 1)

    @staticmethod
    def angle_interval(direction0, direction1):
        return abs(direction0.angle() - direction1.angle())


class Meters(Quantity):
    """
    Numbers with units
    """

    @classmethod
    def __get_validators__(cls):
        # one or more validators may be yielded which will be called in the
        # order to validate the input, each validator will receive as an input
        # the value returned from the previous validator
        yield cls.validate
        yield cls.transform_units
        yield cls.to_magnitude

    @classmethod
    def validate(cls, v):
        if isinstance(v, str):
            q = unit_registry.parse_expression(v)
        else:
            q = Quantity(v, "meter")
        return cls(q.magnitude, q.units)

    @classmethod
    def transform_units(cls, v):
        q = v.to("m")
        return cls(q.magnitude, q.units)

    @classmethod
    def to_magnitude(cls, v: Quantity):
        return v.magnitude

    def __repr__(self):
        return f"{self:~P}"


class TopologyBase(BaseModel):
    perimeter_zone_depth: Optional[Meters] = "15 ft"
    building_orientation: Direction = Direction.NORTH
    building_aspect_ratio: Optional[PositiveFloat] = None
    floor_to_floor: Meters = "12 ft"

    class Config:
        validate_assignment = True
        validate_all = True
        extra = Extra.allow

    @property
    def coords(self):
        raise NotImplemented

    @property
    def shapely_polygon(self):
        from shapely.geometry import Polygon

        return Polygon(self.coords)

    def validate_shape(self):
        """Validate shape. Uses :func:`~shapely.geometry.base.BaseGeometry.is_valid`."""
        assert self.shapely_polygon.is_valid


class Triangle(TopologyBase):
    """Triangle Shape.

    X1 > 0
    Y1 > 0
    X2 >= 0

    ::
               X2
           ----------
          |        /\
          |       / | \
          |      /  |    \
        Y1|     /   |       \
          |    /    |          \
          |   /     |            \
          |  /      |               \
          | --------+-----------------\
                        X1
    """

    X1: Optional[Meters] = "223.6 ft"
    X2: Optional[Meters] = "67.10 ft"
    Y1: Optional[Meters] = "111.80 ft"

    @root_validator()
    def validate_points(cls, v):
        """Validate points."""
        assert v["X1"] > 0, "X1 > 0"
        assert v["Y1"] > 0, "Y1 > 0"
        return v

    @property
    def coords(self):
        return [
            (0, 0),
            (self.X1, 0),
            (self.X2, self.Y1),
            (0, 0),
        ]


class Rectangle(TopologyBase):
    """Rectangle shape.

    X1 > 0
    Y1 > 0

    ::
         |  +-------------------+
         |  |                   |
         |  |                   |
         |  |                   |
        Y1  |                   |
         |  |                   |
         |  |                   |
         |  +-------------------+
            ---------X1----------
    """

    X1: Optional[Meters] = "111.80 ft"
    Y1: Optional[Meters] = "111.80 ft"

    @root_validator()
    def validate_points(cls, v):
        """Validate points."""
        assert v["X1"] > 0, "X1 > 0"
        assert v["Y1"] > 0, "Y1 > 0"
        return v

    @property
    def coords(self):
        return [(0, 0), (self.X1, 0), (self.X1, self.Y1), (0, self.Y1), (0, 0)]


class Trapezoid(TopologyBase):
    """
    ::
         <----X3---->+<-------X2-------->
         ^           /------------------\\
         |          //                   \\
         |          /                     \\
         |         //                      \\
         |        //                        \\
         |        /                          \\
        Y1       //                           \\
         |      //                             \\
         |     //                               \\
         |    //                                 \\
         |    /                                   \
         |   //                                   \\
         v  /--------------------------------------\\
            <------------------X1------------------>

    """

    X1: Optional[Meters] = "175.35 ft"
    X2: Optional[Meters] = "109.80 ft"
    X3: Optional[Meters] = "32.80 ft"
    Y1: Optional[Meters] = "87.70 ft"

    @root_validator()
    def validate_points(cls, v):
        """Validate points."""
        assert v["X1"] > 0, "X1 > 0"
        assert v["X2"] > 0, "X2 > 0"
        assert v["X3"] >= 0, "X3 >= 0"
        assert v["Y1"] > 0, "Y1 > 0"
        return v

    @property
    def coords(self):
        return [
            (0, 0),
            (self.X1, 0),
            (self.X3 + self.X2, self.Y1),
            (self.X3, self.Y1),
            (0, 0),
        ]


class L_Shape(TopologyBase):
    """
    ::
            <-----X2------>
         ^  +-------------+
         |  |             |
         |  |             |
         |  |             |
         |  |             |
         |  |             |
        Y1  |             +----------------+  ^
         |  |                              |  |
         |  |                              |  |
         |  |                              |  Y2
         |  |                              |  |
         |  |                              |  |
         v  +------------------------------+  v
            <--------------X1-------------->
    """

    X1: Optional[Meters] = "134.15 ft"
    X2: Optional[Meters] = "60.00 ft"
    Y1: Optional[Meters] = "134.15 ft"
    Y2: Optional[Meters] = "60.00 ft"

    @root_validator()
    def validate_points(cls, v):
        """Validate points."""
        assert v["X1"] > 0, "X1 > 0"
        assert v["X1"] > v["X2"], "X1 > X2"
        assert v["X2"] > 0, "X2 > 0"
        assert v["Y1"] > 0, "Y1 > 0"
        assert v["Y1"] > v["Y2"], "Y1 > Y2"
        assert v["Y2"] > 0, "Y2 > 0"
        return v

    @property
    def coords(self):
        return [
            (0, 0),
            (self.X1, 0),
            (self.X1, self.Y2),
            (self.X2, self.Y2),
            (self.X2, self.Y1),
            (0, self.Y1),
            (0, 0),
        ]


class T_Shape(TopologyBase):
    """
    ::
         <-----X2------->+<-----X3----->
         ^               +-------------+               ^
         |               |             |               |
         |               |             |               |
         |               |             |               Y2
         |               |             |               |
        Y1               |             |               |
         | +-------------+             +-------------+ v
         | |                                         |
         | |                                         |
         | |                                         |
         | |                                         |
         | |                                         |
         v +-----------------------------------------+
           <--------------------X1------------------->
    """

    X1: Optional[Meters] = "152.80 ft"
    X2: Optional[Meters] = "45.00 ft"
    X3: Optional[Meters] = "62.75 ft"
    Y1: Optional[Meters] = "109.15 ft"
    Y2: Optional[Meters] = "46.40 ft"

    @root_validator()
    def validate_points(cls, v):
        """Validate points."""
        assert v["X1"] > 0, "X1 > 0"
        assert v["X1"] > v["X2"] + v["X3"], "X1 > X2 + X3"
        assert v["X1"] > v["X2"]
        assert v["X2"] > 0, "X2 > 0"
        assert v["X3"] > 0, "X3 > 0"
        assert v["Y1"] > 0, "Y1 > 0"
        assert v["Y1"] > v["Y2"], "Y1 > Y2"
        assert v["Y2"] > 0, "Y2 > 0"
        return v

    @property
    def coords(self):
        return [
            (0, 0),
            (self.X1, 0),
            (self.X1, self.Y1 - self.Y2),
            (self.X2 + self.X3, self.Y1 - self.Y2),
            (self.X2 + self.X3, self.Y1),
            (self.X2, self.Y1),
            (self.X2, self.Y1 - self.Y2),
            (0, self.Y1 - self.Y2),
            (0, 0),
        ]


class CrossShape(TopologyBase):
    """
    ::
         <-------X2-------->+<-----X3------->
         ^                  +---------------+
         |                  |               |
         |                  |               |
         |                  |               |
         |                  |               |
         |                  |               |
         |  +---------------+               +---------------+  ^
         |  |                                               |  |
         |  |                                               |  |
        Y1  |                                               |  Y3
         |  |                                               |  |
         |  |                                               |  v
         |  +---------------+               +---------------+  +
         |                  |               |                  ^
         |                  |               |                  |
         |                  |               |                 Y2
         |                  |               |                  |
         |                  |               |                  |
         v                  +---------------+                  v
         <-------------------------X1----------------------->
    """

    X1: Optional[Meters] = "150 ft"
    X2: Optional[Meters] = "50 ft"
    X3: Optional[Meters] = "50 ft"
    Y1: Optional[Meters] = "150 ft"
    Y2: Optional[Meters] = "50 ft"
    Y3: Optional[Meters] = "50 ft"

    @root_validator()
    def validate_points(cls, v):
        """Validate points."""
        assert v["X1"] > 0, "X1 > 0"
        assert v["X1"] > v["X2"] + v["X3"], "X1 > X2 + X3"
        assert v["X2"] > 0, "X2 > 0"
        assert v["X3"] > 0, "X3 > 0"
        assert v["Y1"] > 0, "Y1 > 0"
        assert v["Y1"] > v["Y2"], "Y1 > Y2"
        assert v["Y2"] > 0, "Y2 > 0"
        assert v["Y3"] > 0, "Y3 > 0"
        return v

    @property
    def coords(self):
        return [
            (self.X2, 0),
            (self.X2 + self.X3, 0),
            (self.X2 + self.X3, self.Y2),
            (self.X1, self.Y2),
            (self.X1, self.Y2 + self.Y3),
            (self.X2 + self.X3, self.Y3 + self.Y2),
            (self.X2 + self.X3, self.Y1),
            (self.X2, self.Y1),
            (self.X2, self.Y2 + self.Y3),
            (0, self.Y2 + self.Y3),
            (0, self.Y3),
            (self.X2, self.Y2),
            (self.X2, 0),
        ]


class U_Shape(TopologyBase):
    X1: Optional[Meters] = "149.20 ft"
    X2: Optional[Meters] = "55.75 ft"
    X3: Optional[Meters] = "55.75 ft"
    Y1: Optional[Meters] = "93.25 ft"
    Y2: Optional[Meters] = "93.25 ft"
    Y3: Optional[Meters] = "55.75 ft"

    @root_validator()
    def validate_points(cls, v):
        """Validate points."""
        assert v["X1"] > 0, "X1 > 0"
        assert v["X1"] > v["X2"] + v["X3"], "X1 > X2 + X3"
        assert v["X1"] > v["X2"], "X1 > 0"
        assert v["X2"] > 0, "X2 > 0"
        assert v["X3"] > 0, "X3 > 0"
        assert v["Y1"] > 0, "Y1 > 0"
        assert v["Y1"] > v["Y3"], "Y1 > Y3"
        assert v["Y2"] > 0, "Y2 > 0"
        assert v["Y2"] > v["Y3"], "Y2 > Y3"
        assert v["Y3"] > 0, "Y3 > 0"
        return v

    @property
    def coords(self):
        return [
            (0, 0),
            (self.X1, 0),
            (self.X1, self.Y2),
            (self.X1 - self.X3, self.Y2),
            (self.X1 - self.X3, self.Y3),
            (self.X2, self.Y3),
            (self.X2, self.Y1),
            (0, self.Y1),
            (0, 0),
        ]


class H_Shape(TopologyBase):
    X1: Optional[Meters] = "128.75 ft"
    X2: Optional[Meters] = "46.25 ft"
    X3: Optional[Meters] = "36.30 ft"
    Y1: Optional[Meters] = "117.05 ft"
    Y2: Optional[Meters] = "35.40 ft"
    Y3: Optional[Meters] = "46.25 ft"

    @root_validator()
    def validate_points(cls, v):
        """Validate points."""
        assert v["X1"] > 0, "X1 > 0"
        assert v["X1"] > v["X2"] + v["X3"], "X1 > X2 + X3"
        assert v["X1"] > v["X2"], "X1 > X2"
        assert v["X2"] > 0, "X2 > 0"
        assert v["X3"] > 0, "X3 > 0"
        assert v["Y1"] > 0, "Y1 > 0"
        assert v["Y2"] > 0, "Y2 > 0"
        assert v["Y3"] > 0, "Y3 > 0"
        assert v["Y1"] > v["Y2"], "Y1 > Y2"
        return v

    @property
    def coords(self):
        return [
            (0, 0),
            (self.X2, 0),
            (self.X2, self.Y2),
            (self.X2 + self.X3, self.Y2),
            (self.X2 + self.X3, 0),
            (self.X1, 0),
            (self.X1, self.Y1),
            (self.X2 + self.X3, self.Y1),
            (self.X2 + self.X3, self.Y2 + self.Y3),
            (self.X2, self.Y2 + self.Y3),
            (self.X2, self.Y1),
            (0, self.Y1),
            (0, 0),
        ]


# class RectangularAtrium(TopologyBase):
#     X1: Optional[Meters] = "118.60 ft"
#     X2: Optional[Meters] = "39.50 ft"
#     X3: Optional[Meters] = "39.50 ft"
#     Y1: Optional[Meters] = "118.60 ft"
#     Y2: Optional[Meters] = "39.50 ft"
#     Y3: Optional[Meters] = "39.50 ft"
#
#     @property
#     def coords(self):
#         return [
#             (0, 0),
#             (self.X1, 0),
#             (self.X1, self.Y1),
#             (0, self.Y1),
#             (0, self.Y2),
#             (self.X2, self.Y2),
#             (self.X2, self.Y1 - self.Y3),
#             (self.X1 - self.X3, self.Y1 - self.Y3),
#             (self.X1 - self.X3, self.Y2),
#             (self.X2, self.Y2),
#             (0, self.Y2),
#             (0, 0),
#         ]
