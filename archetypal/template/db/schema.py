import json
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Relationship, Session, MetaData, select
from sqlmodel.typing import SQLModelConfig as ConfigDict


class GenericMaterialBase(SQLModel):
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
    )

    SpecificHeat: float = Field(
        ...,
        ge=100,
        le=2000,
        title="Specific Heat",
        description="Specific Heat 'C_p', in J/(kg*K) of material",
    )


class MaterialLayerBase(SQLModel):
    """
    Material Layers are Used to build up Assemblies.
    """

    model_config = ConfigDict(title="Material Layer")

    Thickness: float = Field(
        ...,
        ge=0.003,
        title="Thickness",
        description="Thickness of this layer",
    )


class ConstructionBase(SQLModel):
    """
    A Construction is a set of Material Layers that represent an assembly.
    """

    model_config = ConfigDict(title="Construction")


class ConstructionSetBase(SQLModel):
    """
    A Zone Construction Set defines the assemblies for the walls, roofs, etc that make up
    the envelope of a zone.
    """

    model_config = ConfigDict(title="Zone Construction Set")


class ZoneBase(SQLModel):
    """
    A Zone Definition represents a single zone within an Energy Model.
    """

    model_config = ConfigDict(title="Zone Definition")

    DaylightWorkplaneHeight: float = Field(
        0.8,
        ge=0,
        title="Daylight Workplane Height",
        description="Offset for workplane height in daylight simulations",
    )


class TemplateBase(SQLModel):
    """
    An UMI Template is a building simulation archetype which will be used to create
    shoebox energy model definitions for each building assigned to that archetype
    in an UMI simulation.
    """

    model_config = ConfigDict(title="UMI Template")

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
    )


class LibraryBase(SQLModel):
    """
    An UMI Template Library represents a collection of templates which will
    be used in an UMI simulation.  Each UMI Template is an archetype which
    will be used to generate shoebox energy models for all buildings assigned
    to that archetype.
    """

    model_config = ConfigDict(
        title="UMI Template Library",
    )

    Creator: str = Field(..., description="Author of Lirary", title='Creator')


class GenericMaterial(GenericMaterialBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    Layers: list["MaterialLayer"] = Relationship(back_populates="Material")


class MaterialLayerConstructionLink(SQLModel, table=True):
    MaterialLayer_id: Optional[int] = Field(
        default=None,
        foreign_key="materiallayer.id",
        primary_key=True,
    )
    Construction_id: Optional[int] = Field(
        default=None,
        foreign_key="construction.id",
        primary_key=True,
    )


class MaterialLayer(MaterialLayerBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    Material_id: int = Field(
        ...,
        title="Material ID",
        description="ID of material used in this layer.",
        foreign_key="genericmaterial.id",
    )
    Material: GenericMaterial = Relationship(back_populates="Layers")
    Constructions: list["Construction"] = Relationship(
        back_populates="Layers",
        link_model=MaterialLayerConstructionLink,
    )


class Construction(ConstructionBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # See https://github.com/tiangolo/sqlmodel/issues/10 for overview of this pattern
    Layers: list[MaterialLayer] = Relationship(
        back_populates="Constructions",
        link_model=MaterialLayerConstructionLink,
    )

    Partitions: list["ConstructionSet"] = Relationship(
        back_populates="Partition",
        sa_relationship_kwargs=dict(
            primaryjoin="ConstructionSet.Partition_id==Construction.id",
            lazy="joined",
        ),
    )
    Roofs: list["ConstructionSet"] = Relationship(
        back_populates="Roof",
        sa_relationship_kwargs=dict(
            primaryjoin="ConstructionSet.Roof_id==Construction.id",
            lazy="joined",
        ),
    )
    Grounds: list["ConstructionSet"] = Relationship(
        back_populates="Ground",
        sa_relationship_kwargs=dict(
            primaryjoin="ConstructionSet.Ground_id==Construction.id",
            lazy="joined",
        ),
    )
    Slabs: list["ConstructionSet"] = Relationship(
        back_populates="Slab",
        sa_relationship_kwargs=dict(
            primaryjoin="ConstructionSet.Slab_id==Construction.id",
            lazy="joined",
        ),
    )
    Walls: list["ConstructionSet"] = Relationship(
        back_populates="Wall",
        sa_relationship_kwargs=dict(
            primaryjoin="ConstructionSet.Wall_id==Construction.id",
            lazy="joined",
        ),
    )


class ConstructionSet(ConstructionSetBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    Partition_id: Optional[int] = Field(
        ...,
        description="Id for construction assembly for interior partition walls;"
        "used to divide Perimeter and Core Zones.",
        foreign_key="construction.id",
    )
    Partition: Construction = Relationship(
        back_populates="Partitions",
        sa_relationship_kwargs=dict(
            foreign_keys="[ConstructionSet.Partition_id]",
        ),
    )

    Roof_id: Optional[int] = Field(
        ...,
        description="ID Construction assembly for roof",
        foreign_key="construction.id",
    )
    Roof: Construction = Relationship(
        back_populates="Roofs",
        sa_relationship_kwargs=dict(
            foreign_keys="[ConstructionSet.Roof_id]",
        ),
    )

    Ground_id: Optional[int] = Field(
        ...,
        description="ID for Construction assembly for ground",
        foreign_key="construction.id",
    )
    Ground: Construction = Relationship(
        back_populates="Grounds",
        sa_relationship_kwargs=dict(
            foreign_keys="[ConstructionSet.Ground_id]",
        ),
    )

    Slab_id: Optional[int] = Field(
        ...,
        description="ID for Construction assembly for slabs",
        foreign_key="construction.id",
    )
    Slab: Construction = Relationship(
        back_populates="Slabs",
        sa_relationship_kwargs=dict(
            foreign_keys="[ConstructionSet.Slab_id]",
        ),
    )

    Wall_id: Optional[int] = Field(
        ...,
        description="ID for Construction assembly for exterior walls",
        foreign_key="construction.id",
    )
    Wall: Construction = Relationship(
        back_populates="Walls",
        sa_relationship_kwargs=dict(
            foreign_keys="[ConstructionSet.Wall_id]",
        ),
    )

    Zones: list["Zone"] = Relationship(back_populates="Constructions")


class Zone(ZoneBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    Constructions_id: Optional[int] = Field(
        ...,
        title="Zone Construction Set",
        description="Assembly definitions for the zone's envelope,"
        " i.e. exterior walls, partition walls, etc.",
        foreign_key="constructionset.id",
    )

    Constructions: ConstructionSet = Relationship(back_populates="Zones")

    Perimeters: list["Template"] = Relationship(
        back_populates="Perimeter",
        sa_relationship_kwargs=dict(
            primaryjoin="Template.Perimeter_id==Zone.id",
            lazy="joined",
        ),
    )
    Cores: list["Template"] = Relationship(
        back_populates="Core",
        sa_relationship_kwargs=dict(
            primaryjoin="Template.Core_id==Zone.id",
            lazy="joined",
        ),
    )


class TemplateLibraryLink(SQLModel, table=True):
    Template_id: Optional[int] = Field(
        default=None,
        foreign_key="template.id",
        primary_key=True,
    )
    Library_id: Optional[int] = Field(
        default=None,
        foreign_key="library.id",
        primary_key=True,
    )


class Template(TemplateBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    Perimeter_id: Optional[int] = Field(
        ...,
        description="ID for perimeter zone definition",
        foreign_key="zone.id",
    )
    Perimeter: Zone = Relationship(
        back_populates="Perimeters",
        sa_relationship_kwargs=dict(
            foreign_keys="[Template.Perimeter_id]",
        ),
    )

    Core_id: Optional[int] = Field(
        ...,
        description="ID for perimeter zone definition",
        foreign_key="zone.id",
    )
    Core: Zone = Relationship(
        back_populates="Cores",
        sa_relationship_kwargs=dict(
            foreign_keys="[Template.Core_id]",
        ),
    )

    Libraries: list["Library"] = Relationship(
        back_populates="Templates",
        link_model=TemplateLibraryLink,
    )


class Library(LibraryBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    Templates: list[Template] = Relationship(
        back_populates="Libraries",
        link_model=TemplateLibraryLink,
    )


def schema_to_json(engine, metadata: MetaData):
    tables = {}
    for table in metadata.sorted_tables:
        columns = {}
        for column in table.columns:
            columns[column.name] = {
                "type": str(column.type),
                "primary_key": column.primary_key,
                "nullable": column.nullable,
                "default": str(column.default),
                "foreign_key": str(list(column.foreign_keys)[0])
                if len(column.foreign_keys) == 1
                else None,
            }
        tables[table.name] = columns
    return json.dumps(tables, indent=4)


if __name__=="__main__":
    engine = create_engine("sqlite:///database.db")


    SQLModel.metadata.create_all(engine)


    with Session(engine) as session:
        construction = Construction(
            Layers=[
                MaterialLayer(
                    Thickness=0.3,
                    Material=GenericMaterial(Conductivity=1, SpecificHeat=800),
                ),
                MaterialLayer(
                    Thickness=0.1,
                    Material=GenericMaterial(Conductivity=2, SpecificHeat=400),
                ),
            ]
        )

        construction_set = ConstructionSet(
            Partition=construction,
            Roof=construction,
            Ground=construction,
            Slab=construction,
            Wall=construction,
        )
        zone = Zone(DaylightWorkplaneHeight=0.1, Constructions=construction_set)

        lib = Library(
            Creator ="szvsw",
            Templates=[
                Template(
                    Perimeter=zone,
                    Core=zone,
                    YearFrom=2000,
                    YearTo=2001,
                    Country="USA",
                ),
                Template(
                    Perimeter=zone,
                    Core=zone,
                    YearFrom=2010,
                    YearTo=2020,
                    Country="UK",
                ),
            ]
        )
        session.add(lib)
        session.commit()


    with engine.connect():
        schema_json = schema_to_json(engine, SQLModel.metadata)
        with open("db_schema.json",'w') as f:
            f.write(schema_json)
    
    with Session(engine) as session:
        lib = session.exec(select(Library)).first()
        print(lib.Templates[0].Perimeter.Constructions.Slab.Layers)