"""Tests for the new archetypal parser (v3)."""

from __future__ import annotations

import pytest
from io import StringIO
from pathlib import Path

from archetypal.idfclass.parser import (
    IDFObject,
    IDFCollection,
    IDFDocument,
    parse_idf,
    write_idf,
    write_epjson,
    ValidationResult,
    validate_document,
    get_idf_version,
    ReferenceGraph,
)
from archetypal.idfclass.parser.geometry import Vector3D, Polygon3D


class TestIDFObject:
    """Tests for IDFObject class."""

    def test_create_object(self):
        """Test creating an IDFObject."""
        obj = IDFObject(
            obj_type="Zone",
            name="TestZone",
            data={"direction_of_relative_north": 0.0, "x_origin": 10.0},
        )

        assert obj._type == "Zone"
        assert obj.name == "TestZone"
        assert obj.Name == "TestZone"  # eppy compatibility
        assert obj.direction_of_relative_north == 0.0
        assert obj.x_origin == 10.0

    def test_attribute_access(self):
        """Test attribute access patterns."""
        obj = IDFObject(
            obj_type="Material",
            name="TestMaterial",
            data={
                "roughness": "Rough",
                "thickness": 0.1,
                "conductivity": 1.0,
            },
        )

        # Direct access
        assert obj.roughness == "Rough"
        assert obj.thickness == 0.1

        # Case variations should work
        assert obj.Roughness == "Rough"
        assert obj.ROUGHNESS is None  # Not found (case sensitive in data)

    def test_field_names_and_values(self):
        """Test fieldnames and fieldvalues properties."""
        obj = IDFObject(
            obj_type="Zone",
            name="Zone1",
            data={"multiplier": 1, "x_origin": 0.0},
            field_order=["multiplier", "x_origin"],
        )

        assert "Name" in obj.fieldnames
        assert obj.fieldvalues[0] == "Zone1"

    def test_equality(self):
        """Test object equality."""
        obj1 = IDFObject("Zone", "Zone1", {"x_origin": 0.0})
        obj2 = IDFObject("Zone", "Zone1", {"x_origin": 0.0})
        obj3 = IDFObject("Zone", "Zone2", {"x_origin": 0.0})

        assert obj1 == obj2
        assert obj1 != obj3

    def test_copy(self):
        """Test object copying."""
        obj = IDFObject("Zone", "Zone1", {"x_origin": 10.0})
        copy = obj.copy()

        assert copy == obj
        assert copy is not obj
        assert copy._data is not obj._data

    def test_to_dict(self):
        """Test conversion to dict."""
        obj = IDFObject("Zone", "Zone1", {"x_origin": 10.0, "y_origin": 20.0})
        d = obj.to_dict()

        assert d["name"] == "Zone1"
        assert d["x_origin"] == 10.0
        assert d["y_origin"] == 20.0


class TestIDFCollection:
    """Tests for IDFCollection class."""

    def test_create_collection(self):
        """Test creating a collection."""
        coll = IDFCollection("Zone")
        assert len(coll) == 0
        assert coll._type == "Zone"

    def test_add_object(self):
        """Test adding objects to collection."""
        coll = IDFCollection("Zone")
        obj = IDFObject("Zone", "Zone1", {})
        coll.add(obj)

        assert len(coll) == 1
        assert "Zone1" in coll
        assert coll["Zone1"] == obj

    def test_duplicate_name_error(self):
        """Test that duplicate names raise error."""
        from archetypal.idfclass.parser.exceptions import DuplicateObjectError

        coll = IDFCollection("Zone")
        coll.add(IDFObject("Zone", "Zone1", {}))

        with pytest.raises(DuplicateObjectError):
            coll.add(IDFObject("Zone", "Zone1", {}))

    def test_iteration(self):
        """Test iterating over collection."""
        coll = IDFCollection("Zone")
        coll.add(IDFObject("Zone", "Zone1", {}))
        coll.add(IDFObject("Zone", "Zone2", {}))

        names = [obj.name for obj in coll]
        assert names == ["Zone1", "Zone2"]

    def test_case_insensitive_lookup(self):
        """Test case-insensitive name lookup."""
        coll = IDFCollection("Zone")
        coll.add(IDFObject("Zone", "Zone1", {}))

        assert coll["zone1"] == coll["ZONE1"] == coll["Zone1"]


class TestIDFDocument:
    """Tests for IDFDocument class."""

    def test_create_document(self):
        """Test creating a document."""
        doc = IDFDocument(version=(23, 2, 0))

        assert doc.version == (23, 2, 0)
        assert len(doc) == 0

    def test_add_objects(self):
        """Test adding objects to document."""
        doc = IDFDocument(version=(23, 2, 0))
        doc.add("Zone", "Zone1", {"x_origin": 10.0})
        doc.add("Zone", "Zone2", {"x_origin": 20.0})

        assert len(doc["Zone"]) == 2
        assert doc["Zone"]["Zone1"].x_origin == 10.0

    def test_idfobjects_compatibility(self):
        """Test idfobjects dict-like access."""
        doc = IDFDocument(version=(23, 2, 0))
        doc.add("Zone", "Zone1", {})

        # Should work with different cases
        assert len(doc.idfobjects["Zone"]) == 1
        assert len(doc.idfobjects["ZONE"]) == 1

    def test_schedules_dict(self):
        """Test schedules_dict property."""
        doc = IDFDocument(version=(23, 2, 0))
        doc.add("Schedule:Constant", "AlwaysOn", {"hourly_value": 1.0})
        doc.add("Schedule:Compact", "Occupancy", {})

        scheds = doc.schedules_dict
        assert "ALWAYSON" in scheds
        assert "OCCUPANCY" in scheds

    def test_copy(self):
        """Test document copying."""
        doc = IDFDocument(version=(23, 2, 0))
        doc.add("Zone", "Zone1", {"x_origin": 10.0})

        copy = doc.copy()
        assert len(copy) == len(doc)
        assert copy["Zone"]["Zone1"].x_origin == 10.0

        # Modifying copy shouldn't affect original
        copy["Zone"]["Zone1"].x_origin = 20.0
        assert doc["Zone"]["Zone1"].x_origin == 10.0


class TestReferenceGraph:
    """Tests for ReferenceGraph class."""

    def test_register_reference(self):
        """Test registering references."""
        graph = ReferenceGraph()
        obj = IDFObject("BuildingSurface:Detailed", "Wall1", {"zone_name": "Zone1"})

        graph.register(obj, "zone_name", "Zone1")

        assert obj in graph.get_referencing("Zone1")
        assert "ZONE1" in graph.get_references(obj)

    def test_unregister(self):
        """Test unregistering references."""
        graph = ReferenceGraph()
        obj = IDFObject("BuildingSurface:Detailed", "Wall1", {})
        graph.register(obj, "zone_name", "Zone1")

        graph.unregister(obj)

        assert len(graph.get_referencing("Zone1")) == 0


class TestGeometry:
    """Tests for geometry utilities."""

    def test_vector_operations(self):
        """Test Vector3D operations."""
        v1 = Vector3D(1.0, 2.0, 3.0)
        v2 = Vector3D(4.0, 5.0, 6.0)

        # Addition
        result = v1 + v2
        assert result == Vector3D(5.0, 7.0, 9.0)

        # Subtraction
        result = v2 - v1
        assert result == Vector3D(3.0, 3.0, 3.0)

        # Scalar multiplication
        result = v1 * 2
        assert result == Vector3D(2.0, 4.0, 6.0)

        # Dot product
        assert v1.dot(v2) == 32.0  # 1*4 + 2*5 + 3*6

    def test_polygon_area(self):
        """Test polygon area calculation."""
        # Unit square
        vertices = [
            Vector3D(0, 0, 0),
            Vector3D(1, 0, 0),
            Vector3D(1, 1, 0),
            Vector3D(0, 1, 0),
        ]
        poly = Polygon3D(vertices)

        assert abs(poly.area - 1.0) < 0.001

    def test_polygon_centroid(self):
        """Test polygon centroid calculation."""
        vertices = [
            Vector3D(0, 0, 0),
            Vector3D(2, 0, 0),
            Vector3D(2, 2, 0),
            Vector3D(0, 2, 0),
        ]
        poly = Polygon3D(vertices)

        centroid = poly.centroid
        assert abs(centroid.x - 1.0) < 0.001
        assert abs(centroid.y - 1.0) < 0.001


class TestIDFParser:
    """Tests for IDF parsing."""

    def test_parse_minimal_idf(self, tmp_path):
        """Test parsing a minimal IDF file."""
        idf_content = """
        Version,
          23.2;

        Zone,
          TestZone,                !- Name
          0,                       !- Direction of Relative North
          0, 0, 0,                 !- X,Y,Z Origin
          1,                       !- Type
          1;                       !- Multiplier
        """

        idf_path = tmp_path / "test.idf"
        idf_path.write_text(idf_content)

        doc = parse_idf(idf_path)

        assert doc.version == (23, 2, 0)
        assert len(doc["Zone"]) == 1
        assert doc["Zone"]["TestZone"].name == "TestZone"

    def test_parse_multiple_objects(self, tmp_path):
        """Test parsing multiple objects."""
        idf_content = """
        Version, 23.2;

        Zone, Zone1, 0, 0, 0, 0, 1, 1;
        Zone, Zone2, 0, 10, 0, 0, 1, 1;

        Material,
          Concrete,                !- Name
          Rough,                   !- Roughness
          0.2,                     !- Thickness
          1.0,                     !- Conductivity
          2000,                    !- Density
          900;                     !- Specific Heat
        """

        idf_path = tmp_path / "test.idf"
        idf_path.write_text(idf_content)

        doc = parse_idf(idf_path)

        assert len(doc["Zone"]) == 2
        assert len(doc["Material"]) == 1

    def test_version_detection(self, tmp_path):
        """Test version detection."""
        idf_content = "Version, 9.5;"
        idf_path = tmp_path / "test.idf"
        idf_path.write_text(idf_content)

        version = get_idf_version(idf_path)
        assert version == (9, 5, 0)


class TestIDFWriter:
    """Tests for IDF writing."""

    def test_write_to_string(self):
        """Test writing document to string."""
        doc = IDFDocument(version=(23, 2, 0))
        doc.add("Zone", "TestZone", {"direction_of_relative_north": 0.0})

        content = write_idf(doc, None)

        assert "Zone," in content
        assert "TestZone" in content
        assert "23.2" in content

    def test_roundtrip(self, tmp_path):
        """Test parsing and writing produces equivalent result."""
        idf_content = """
        Version, 23.2;
        Zone, TestZone, 0, 0, 0, 0, 1, 1;
        """

        idf_path = tmp_path / "original.idf"
        idf_path.write_text(idf_content)

        # Parse
        doc = parse_idf(idf_path)

        # Write
        output_path = tmp_path / "output.idf"
        write_idf(doc, output_path)

        # Parse again
        doc2 = parse_idf(output_path)

        # Check equivalence
        assert doc.version == doc2.version
        assert len(doc["Zone"]) == len(doc2["Zone"])


class TestEpJSONWriter:
    """Tests for epJSON writing."""

    def test_write_to_dict(self):
        """Test writing document to epJSON dict."""
        doc = IDFDocument(version=(23, 2, 0))
        doc.add("Zone", "TestZone", {"direction_of_relative_north": 0.0})

        from archetypal.idfclass.parser.writers import EpJSONWriter

        writer = EpJSONWriter(doc)
        data = writer.to_dict()

        assert "Version" in data
        assert "Zone" in data
        assert "TestZone" in data["Zone"]


# Integration test with actual test files
class TestIntegration:
    """Integration tests with real IDF files."""

    @pytest.fixture
    def test_idf_path(self):
        """Get path to test IDF file if available."""
        test_dir = Path(__file__).parent / "input_data"
        idf_files = list(test_dir.rglob("*.idf"))
        if idf_files:
            return idf_files[0]
        return None

    def test_parse_real_file(self, test_idf_path):
        """Test parsing a real IDF file."""
        if test_idf_path is None:
            pytest.skip("No test IDF files available")

        doc = parse_idf(test_idf_path)

        assert doc.version[0] >= 8  # At least version 8
        assert len(doc) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
