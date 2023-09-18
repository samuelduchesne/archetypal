import json
from enum import Enum
from typing import Any, Union, ClassVar, TypeVar, Generic
from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    UUID4,
    model_validator,
    field_validator,
    ValidationInfo,
    field_serializer,
    computed_field
)
from uuid import uuid4
import networkx as nx


class UmiBase(BaseModel, validate_assignment=True):
    all: ClassVar[dict[int, "UmiBase"]] = {}
    graph: ClassVar[nx.MultiDiGraph] = nx.MultiDiGraph()

    id: UUID4 = Field(..., default_factory=uuid4, title="Object ID")

    @field_serializer("id", when_used="always")
    def serialize_id(val, info):
        return str(val)

    def __hash__(self):
        return self.id.int

    @model_validator(mode="after")
    def cache_item(self, v: ValidationInfo):
        """
        When objects are created, they are either fetched from the cache
        if the ID exists already, otherwise they are added to the cache
        """

        node = self
        if self.id.int not in UmiBase.all:
            UmiBase.all[self.id.int] = self
            UmiBase.graph.add_node(self)
        else:
            node = UmiBase.all[self.id.int]
        
        children = list(UmiBase.graph.successors(self))
        for child in children:
            UmiBase.graph.remove_edge(u=self,v=child)
        nodedict = node.model_dump()
        for field in nodedict.keys():
            other = getattr(node,field) 
            if isinstance(other, UmiBase):
                UmiBase.graph.add_edge(u_for_edge=node, v_for_edge=other, key=field)
        
        return node

    @classmethod
    def classes(cls):
        """
        Return a key/class dict of all UmiBase classes.
        """
        umiclasses = {}
        for umiclass in cls.__subclasses__():
            umiclasses[umiclass.__name__] = umiclass

        return umiclasses

    @classmethod
    def flat_serialization(cls, as_json: bool = False):
        """
        This generates a dictionary similarly to the old style of archetypal objects,
        i.e. each object type is its own key, and other UMI Objects are stored by reference.
        """

        # Prepare a dictionary of all objects
        all_objects = {}

        for item in cls.all.values():
            # If the particular item's class has not yet been registered
            # in the dictionary, register it
            if item.__class__.__name__ not in all_objects:
                all_objects[item.__class__.__name__] = []

            # Generate a dictionary of this particular object
            # it will be deeply nested non-referentially,
            # but it will have pydantic objects as keys when they are
            # there
            item_dict = item.model_dump()

            # For each key, if it is storing an UMI base object
            # replace it with the id, otherwise leave it alone
            for key in item_dict.keys():
                # get the value associated with a key
                val = getattr(item, key)

                if isinstance(val, UmiBase):
                    # the value is an UmiBase object, so it should be conveted to a
                    # reference dictionary which only contains the id
                    item_dict[key] = val.model_dump(include="id")

                elif isinstance(val, list) and any(
                    [isinstance(item, UmiBase) for item in val]
                ):
                    # the value is a list of UmiBase objects which should be converted
                    item_dict[key] = [item.model_dump(include="id") for item in val]

            # Store the trimmed dictionary
            all_objects[item.__class__.__name__].append(item_dict)

        return all_objects if not as_json else json.dumps(all_objects, indent=4)

    def model_copy(
        self: "UmiBase",
        *,
        update: Union[dict[str, Any], None] = None,
        deep: bool = False,
    ) -> "UmiBase":
        """
        When an object is copied, its id should change.
        """
        if update is None:
            update = {}

        update["id"] = uuid4()

        copied = super().model_copy(update=update, deep=deep)
        copied = copied.model_validate(copied)
        return copied

ListT = TypeVar("ListT",bound=UmiBase)
class UmiList(UmiBase, Generic[ListT]):
    objects: list[ListT] = []

    @model_validator(mode="after",)
    def add_nodes(self, v):
        """Whenever the list changes, we need to update parent/child relationships."""
        children = UmiBase.graph.successors(self)
        for i,child in enumerate(list(children)):
            UmiBase.graph.remove_edge(u=self,v=child)
        for i, child in enumerate(self.objects):
            UmiBase.graph.add_edge(u_for_edge=self, v_for_edge=child, key=i)
        return self

    def clear(self):
        children = list(UmiBase.graph.successors(self))
        for child in children:
            UmiBase.graph.remove_edge(u=self, v=child)
        self.objects = []

    def append(self, obj: ListT):
        self.objects.append(obj)
        UmiBase.graph.add_edge(u_for_edge=self, v_for_edge=obj, key=len(self.objects-1))
    
    def __getitem__(self, ix: int):
        return self.objects[ix]
    
    def __setitem__(self, ix: int, obj: ListT):
        old = self.objects[ix]
        self.objects[ix] = obj
        UmiBase.graph.remove_edge(u=self,v=old, key=ix)
        UmiBase.graph.add_edge(u_for_edge=self,v_for_edge=obj, key=ix)


class NumericSchemaExtra(BaseModel):
    units: str  # This could be an enum of SI or IP units


class MaterialBase(UmiBase):
    """
    Material Definition used in construction assemblies and windows
    """

    model_config = ConfigDict(title="Material Definition")

    Conductivity: float = Field(
        ...,
        ge=0,
        le=5,
        title="Thermal Conductivity",
        description="Thermal conductivity 'k', in W/(m*K) of material",
        json_schema_extra=NumericSchemaExtra(units="W/(m*K)").model_dump(),
    )

    SpecificHeat: float = Field(
        ...,
        ge=100,
        le=2000,
        title="Specific Heat",
        description="Specific Heat 'C_p', in J/(kg*K) of material",
        json_schema_extra=NumericSchemaExtra(units="J/(kg*K)").model_dump(),
    )

    Density: float = Field(
        ...,
        ge=0,
        le=10000,
        title="Density",
        description="Density 'rho', in kg/m^3 of material",
        json_schema_extra=NumericSchemaExtra(units="kg/m^3").model_dump(),
    )

    @computed_field
    @property
    def DiffusionCoefficient(self) -> float:
        return self.Conductivity / (self.Density * self.SpecificHeat)


class MaterialLayer(UmiBase):
    """
    Material Layers are Used to build up Assemblies.
    """

    model_config = ConfigDict(title="Material Layer")

    Thickness: float = Field(
        ...,
        ge=0.003,
        title="Thickness",
        description="Thickness of this layer",
        examples=[0.01, 0.05, 0.006],
        json_schema_extra=NumericSchemaExtra(units="m").model_dump(),
    )

    Material: MaterialBase = Field(
        ...,
        title="Material",
        description="Material used in this layer.",
    )


class Construction(UmiBase):
    """
    A Construction is a set of Material Layers that represent an assembly.
    """

    model_config = ConfigDict(title="Construction")

    Layers: UmiList[MaterialLayer] = Field(
        ...,
        title="Material Layers",
        description="The list of Material Layers which define this construction",
    )


class ConstructionSet(UmiBase):
    """
    A Zone Construction Set defines the assemblies for the walls, roofs, etc that make up
    the envelope of a zone.
    """

    model_config = ConfigDict(title="Zone Construction Set")

    Partition: Construction = Field(
        ...,
        title="Partition Wall",
        description="Construction assembly for interior partition walls;"
        "used to divide Perimeter and Core Zones.",
    )

    Roof: Construction = Field(
        ...,
        title="Parition Wall",
        description="Construction assembly for roof",
    )

    Ground: Construction = Field(
        ...,
        title="Ground",
        description="Construction assembly for ground",
    )

    Slab: Construction = Field(
        ...,
        title="Slab",
        description="Construction assembly for slabs",
    )

    Wall: Construction = Field(
        ...,
        title="Exterior Wall",
        description="Construction assembly for exterior walls",
    )


class Zone(UmiBase):
    """
    A Zone Definition represents a single zone within an Energy Model.
    """

    model_config = ConfigDict(title="Zone Definition")

    DaylightWorkplaneHeight: float = Field(
        0.8,
        ge=0,
        title="Daylight Workplane Height",
        description="Offset for workplane height in daylight simulations",
        examples=[0.8, 0.3],
    )

    Constructions: ConstructionSet = Field(
        ...,
        title="Zone Construction Set",
        description="Assembly definitions for the zone's envelope,"
        " i.e. exterior walls, partition walls, etc.",
    )


class Template(UmiBase):
    """
    An UMI Template is a building simulation archetype which will be used to create
    shoebox energy model definitions for each building assigned to that archetype
    in an UMI simulation.
    """

    model_config = ConfigDict(title="UMI Template")

    Perimeter: Zone = Field(
        ...,
        title="Perimeter Zone",
        description="Zone definition for Perimeter zone",
    )

    Core: Zone = Field(
        ...,
        title="Core Zone",
        description="Zone definition for Core zone",
    )

    YearFrom: int = Field(
        ...,
        ge=1800,
        title="Year From",
        description="Start of range years for which this "
        "UMI Template is applicable.",
    )

    YearTo: int = Field(
        ...,
        ge=1800,
        title="Year To",
        description="End of range years for which this " "UMI Template is applicable.",
    )

    Country: str = Field(
        ...,
        title="Country of Origin",
        description="Country of Origin for the Template",
        examples=["USA", "UK"],
    )


class Library(UmiBase):
    """
    An UMI Template Library represents a collection of templates which will
    be used in an UMI simulation.  Each UMI Template is an archetype which
    will be used to generate shoebox energy models for all buildings assigned
    to that archetype.
    """

    model_config = ConfigDict(
        title="UMI Template Library",
    )

    Templates: UmiList[Template] = Field(
        ...,
        title="UMI Templates",
        description="A list of UMI Templates in the library",
    )
