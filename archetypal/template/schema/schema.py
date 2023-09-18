import json
from enum import Enum
from typing import Any, ClassVar, Generic, TypeVar, Union, get_args
from uuid import UUID, uuid4

import networkx as nx
from pydantic import (
    UUID4,
    BaseModel,
    ConfigDict,
    Field,
    InstanceOf,
    ValidationInfo,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)


class UmiBase(BaseModel, validate_assignment=True):
    """
    UmiBase is a class which all UMI Template Library Objects must inherit from.

    It automatically handles generating unique IDs for objects, changing IDs when objects are copied,
    adding objects to a global cache, building and dynamically maintaining a graph, etc.
    """

    all: ClassVar[
        dict[int, "UmiBase"]
    ] = {}  # Class Variable for storing all objects in a hash
    graph: ClassVar[nx.MultiDiGraph] = nx.MultiDiGraph()  # Dynamically updated graph

    id: UUID4 = Field(
        ..., default_factory=uuid4, title="Object ID"
    )  # All objects have a unique id.

    @field_serializer("id", when_used="always")
    def serialize_id(val, info):
        return str(val)

    def __hash__(self):
        return self.id.int

    @model_validator(mode="before")
    def dereference(cls, data: dict[str, Any], info):
        """
        Dereferences an object from the cache if only an id is provided.

        If the data dictionary only has a single key which is an ID
        then we are trying to dereference an object.
        """

        if len(data) == 1 and "id" in data:
            # get the ID
            id = data["id"]

            # Convert it to a UUID
            if isinstance(id, str):
                id = UUID(id)
            elif isinstance(id, UUID):
                pass
            else:
                raise ValueError(
                    f"The value provided for 'id' should be "
                    f"a str or UUID4, not {type(id)}."
                )

            # attempt to dereference
            if id.int in UmiBase.all:
                deref = UmiBase.all[id.int]
                if not isinstance(deref, cls):
                    raise ValueError(
                        f"Attempting to derefence {id} as {cls.__name__}, "
                        f"but found a {deref.__class__.__name__}."
                    )
                data = deref.model_dump()
            else:
                raise ValueError(
                    f"The object was only initialized "
                    f"with an ID so dereferencing was attempted, "
                    f"but the ID provided was not found in the "
                    f"existing object list: ID:{id}"
                )
        return data

    @model_validator(mode="after")
    def cache_item(self, v: ValidationInfo):
        """
        When objects are created, they are either fetched from the cache
        if the ID exists already, otherwise they are added to the cache

        This also handles automatically adding the object to the graph,
        and additionally, connecting the object to any children which it has.
        """

        # Get the object if it exists already, or add it to the cache and graph
        # if not
        node = self
        if self.id.int not in UmiBase.all:
            UmiBase.all[self.id.int] = self
            UmiBase.graph.add_node(self)
        else:
            node = UmiBase.all[self.id.int]

        # Update edges in the graph
        # Get the existing children of the object and remove edges
        children = list(UmiBase.graph.successors(self))
        for child in children:
            UmiBase.graph.remove_edge(u=self, v=child)

        # add edges for all fields which are UmiBase objects
        # TODO: this could possibly be sped up by pre maintaining a list of
        # each field which is an UmiBase field, but it is a very small loop anyways
        # so not super important
        # start by getting a list of fields
        nodedict = node.model_dump()
        for field in nodedict.keys():
            # Get the value for each field and check if it is UmiBase
            other = getattr(node, field)
            if isinstance(other, UmiBase):
                # Add the edge, using the field as the edge label, to allow
                # multiple edges between nodes (e.g. ConstructonSet-:Slab:->Construction)
                UmiBase.graph.add_edge(u_for_edge=node, v_for_edge=other, key=field)

        return node

    @classmethod
    def classes(cls):
        """
        Return a key/class dict of all UmiBase classes.

        This allows getting a list of all UmiClasses indexed by their name
        """
        umiclasses: dict[str, InstanceOf[UmiBase]] = {}
        for umiclass in cls.__subclasses__():
            umiclasses[umiclass.__name__] = umiclass

        return umiclasses

    @classmethod
    def schema_graph(cls):
        """
        Generate a multi di-graph of the schema where each node of the
        graph is an UmiBase class, and each edge is a field of that
        class  which connects it to another class.

        For UmiList fields, the edge is labeled with "index".

        Returns:
            g (nx.MultiDiGraph): The meta-graph of the schema.
        """
        g = nx.MultiDiGraph()
        for umiclass_name, umi_class in cls.classes().items():
            for fieldname, field in umi_class.model_fields.items():
                if field.annotation.__base__ is UmiBase:
                    g.add_edge(
                        u_for_edge=umi_class,
                        v_for_edge=field.annotation,
                        key=fieldname,
                    )
                elif field.annotation.__base__ is UmiList:
                    list_cls = field.annotation
                    target_cls = get_args(
                        field.annotation.model_fields["objects"].annotation
                    )[0]
                    g.add_edge(
                        u_for_edge=umi_class,
                        v_for_edge=list_cls,
                        key=fieldname,
                    )
                    g.add_edge(
                        u_for_edge=list_cls,
                        v_for_edge=target_cls,
                        key="index",
                    )
        return g

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

        # Generate a new id
        update["id"] = uuid4()

        copied = super().model_copy(update=update, deep=deep)
        # Validate is not called on copied objects, but we need validation
        # to run for adding it to the cache and graph
        copied = copied.model_validate(copied)
        return copied


# Generic type; must be populated with a subclass of UmiBase
ListT = TypeVar("ListT", bound=UmiBase)


class UmiList(UmiBase, Generic[ListT]):
    """
    UmiList is responsible for managing fields which are actually list of UmiObjects.

    It is critical for successfully maintaining a dynamically updated graph.

    It addrsses the classic problem that occurs when updating, appending, inserting, etc into a list:

    If e.g. Construction stored its Layers as a plain list, then when a new MaterialLayer is added
    at runtime e.g. with append, it would not trigger any pydantic validation etc, since it would
    just be a list op; there would be no way of knowing that new edge needs to be drawn
    from the Construction to the new MaterialLayer.

    This class resolves that problem, by wrapping a list to enable validation when accessing.

    It can be registed as a field type in another UmiBase model by populating the generic, e.g.:

    Layers: UmiList[MaterialLayer] = Field(,title="List of MaterialLayers")

    """

    objects: list[ListT] = []  # the list to store objects of type ListT

    @model_validator(
        mode="after",
    )
    def add_nodes(self, v):
        """Whenever the list changes, we need to update parent/child relationships."""
        children = UmiBase.graph.successors(self)
        for i, child in enumerate(list(children)):
            UmiBase.graph.remove_edge(u=self, v=child)
        for i, child in enumerate(self.objects):
            # Use the index of the entry as the edge key, e.g. UmiList[MaterialLayers]-:5:->MaterialLayer
            UmiBase.graph.add_edge(u_for_edge=self, v_for_edge=child, key=i)
        return self

    def clear(self):
        children = list(UmiBase.graph.successors(self))
        for child in children:
            UmiBase.graph.remove_edge(u=self, v=child)
        self.objects = []

    def append(self, obj: ListT):
        self.objects.append(obj)
        UmiBase.graph.add_edge(
            u_for_edge=self,
            v_for_edge=obj,
            key=len(self.objects) - 1,
        )

    def insert(self, ix: int, obj: ListT):
        self.objects.insert(ix, obj)
        self.model_validate(self)

    def extend(self, objs: list[ListT]):
        self.objects.extend(objs)
        self.model_validate(self)

    def pop(self, ix: int = -1) -> ListT:
        obj = self.objects.pop(ix)
        self.model_validate(self)
        return obj

    def remove(self, obj: ListT):
        self.objects.remove(obj)
        self.model_validate(self)

    def count(self, obj: ListT) -> int:
        return self.objects.count(obj)

    def __len__(self):
        return len(self.objects)

    def __getitem__(self, ix: int):
        return self.objects[ix]

    def __setitem__(self, ix: int, obj: ListT):
        old = self.objects[ix]
        self.objects[ix] = obj
        UmiBase.graph.remove_edge(u=self, v=old, key=ix)
        UmiBase.graph.add_edge(
            u_for_edge=self,
            v_for_edge=obj,
            key=ix,
        )


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


class ZoneConditioning(UmiBase):
    """
    Represents the definition of the Zone's conditioning system.
    """

    model_config = ConfigDict(title="Zone Conditioning")

    HeatingSetpoint: float = Field(
        70,
        ge=40,
        le=84,
        title="Heating Setpoint",
        description="Heating Setpoint for HVAC Systems",
        examples=[52, 60],
        json_schema_extra=NumericSchemaExtra(units="deg.C"),
    )

    CoolingSetpoint: float = Field(
        76,
        ge=60,
        le=90,
        title="Cooling Setpoint",
        description="Cooling Setpoint for HVAC Systems",
        examples=[75, 80],
        json_schema_extra=NumericSchemaExtra(units="deg.C"),
    )

    @model_validator(mode="before")
    def heating_setpoint_below_cooling_setpoint(cls, v: dict[str, Any], info):
        if v["HeatingSetpoint"] >= v["CoolingSetpoint"]:
            raise ValueError(
                f"The Heating Setpoint {v['HeatingSetpoint']} deg.C is greater than "
                f"the Cooling Setpoint {v['CoolingSetpoint']} deg.C, which is invalid."
            )
        return v


class Zone(UmiBase):
    """
    A Zone Definition represents a single zone within an Energy Model.
    """

    model_config = ConfigDict(title="Zone Definition")

    Conditioning: ZoneConditioning = Field(
        ...,
        title="Zone Conditioning",
        description="Definition of the zone's conditioning systems.",
    )

    DaylightWorkplaneHeight: float = Field(
        0.8,
        ge=0,
        title="Daylight Workplane Height",
        description="Offset for workplane height in daylight simulations",
        examples=[0.8, 0.3],
        json_schema_extra=NumericSchemaExtra(units="m"),
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
