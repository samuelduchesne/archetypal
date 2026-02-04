"""Basic tests for idfkit."""

import tempfile
from pathlib import Path

import pytest


def test_import():
    """Test that the package can be imported."""
    import idfkit
    assert idfkit.__version__ == "0.1.0"


def test_load_idf():
    """Test loading an IDF file."""
    from idfkit import load_idf

    idf_content = """
    Version, 24.1;
    Zone,
      TestZone,              !- Name
      0,                     !- Direction of Relative North
      0, 0, 0,               !- X,Y,Z Origin
      1,                     !- Type
      1;                     !- Multiplier
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".idf", delete=False) as f:
        f.write(idf_content)
        temp_path = Path(f.name)

    try:
        model = load_idf(str(temp_path))
        assert model.version == (24, 1, 0)
        assert len(model["Zone"]) == 1
        assert model["Zone"]["TestZone"].name == "TestZone"
    finally:
        temp_path.unlink()


def test_new_document():
    """Test creating a new document."""
    from idfkit import new_document

    model = new_document(version=(24, 1, 0))
    assert model.version == (24, 1, 0)
    assert len(model) == 0


def test_add_object():
    """Test adding objects to a document."""
    from idfkit import new_document

    model = new_document()
    zone = model.add("Zone", "MyZone", {"x_origin": 10.0})

    assert zone.name == "MyZone"
    assert zone.x_origin == 10.0
    assert len(model["Zone"]) == 1


def test_reference_tracking():
    """Test reference tracking."""
    from idfkit import load_idf

    idf_content = """
    Version, 24.1;
    Zone, TestZone, 0, 0, 0, 0, 1, 1;
    ScheduleTypeLimits, Fraction, 0, 1, Continuous;
    Schedule:Constant, TestSchedule, Fraction, 1.0;
    People,
      TestPeople,            !- Name
      TestZone,              !- Zone Name
      TestSchedule,          !- Schedule Name
      People,                !- Calculation Method
      10;                    !- Number of People
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".idf", delete=False) as f:
        f.write(idf_content)
        temp_path = Path(f.name)

    try:
        model = load_idf(str(temp_path))
        refs = model.get_referencing("TestZone")
        assert len(refs) == 1
        assert list(refs)[0].name == "TestPeople"
    finally:
        temp_path.unlink()


def test_write_idf():
    """Test writing IDF content."""
    from idfkit import new_document, write_idf

    model = new_document()
    model.add("Zone", "MyZone", {"x_origin": 0})

    output = write_idf(model, None)
    assert "Zone," in output
    assert "MyZone" in output
