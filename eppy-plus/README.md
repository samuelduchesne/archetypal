# eppy-plus

A fast, modern EnergyPlus IDF/epJSON parser for Python.

## Features

- **Fast parsing**: 10-90x faster than eppy
- **O(1) lookups**: Hash-based object lookup by name (100-3000x faster than linear scan)
- **Reference tracking**: Instant dependency queries via reference graph
- **Memory efficient**: ~200 bytes per object vs ~1KB in eppy
- **Schema-driven**: Uses EpJSON schema as the single source of truth
- **Type hints**: Full type annotations for IDE support
- **Zero dependencies**: Pure Python, no external dependencies

## Installation

```bash
pip install eppy-plus
```

## Quick Start

```python
from eppy_plus import load_idf, new_document

# Load an existing IDF file
model = load_idf("building.idf")

# Access objects with O(1) lookup
zone = model["Zone"]["MyZone"]
print(f"Zone origin: ({zone.x_origin}, {zone.y_origin}, {zone.z_origin})")

# Find all objects that reference a zone
surfaces = model.get_referencing("MyZone")
print(f"Found {len(surfaces)} surfaces in MyZone")

# Get all schedules actually used in the model
used_schedules = model.get_used_schedules()

# Create a new model
model = new_document(version=(24, 1, 0))
model.add("Zone", "NewZone", {
    "x_origin": 0,
    "y_origin": 0,
    "z_origin": 0,
})

# Save to file
model.save("new_building.idf")
```

## Performance

Benchmarks comparing eppy-plus to eppy on test models:

| Model Size | Parse (eppy-plus) | Parse (eppy) | Speedup | Lookup (eppy-plus) | Lookup (eppy) | Speedup |
|------------|-------------------|--------------|---------|--------------------| --------------|---------|
| 10 zones   | 0.06s            | 5.5s         | 88x     | 0.5 μs            | 37 μs         | 86x     |
| 100 zones  | 0.11s            | 1.3s         | 12x     | 0.5 μs            | 345 μs        | 757x    |
| 500 zones  | 0.52s            | 6.8s         | 13x     | 0.5 μs            | 1656 μs       | 3111x   |

## API Reference

### Loading Files

```python
from eppy_plus import load_idf, load_epjson, new_document

# Load IDF file
model = load_idf("building.idf")

# Load epJSON file
model = load_epjson("building.epJSON")

# Create new empty document
model = new_document(version=(24, 1, 0))
```

### Accessing Objects

```python
# Get collection by type
zones = model["Zone"]
surfaces = model["BuildingSurface:Detailed"]

# Get object by name (O(1) lookup)
zone = zones["MyZone"]

# Iterate over all objects of a type
for zone in model["Zone"]:
    print(zone.name)

# Iterate over all objects
for obj in model.all_objects:
    print(f"{obj._type}: {obj.name}")
```

### Object Attributes

```python
zone = model["Zone"]["MyZone"]

# Access fields as attributes
print(zone.x_origin)
print(zone.direction_of_relative_north)

# Modify fields
zone.x_origin = 10.0

# Get all field data
print(zone._data)
```

### Reference Tracking

```python
# Find all objects that reference a name
surfaces = model.get_referencing("MyZone")

# Get all names that an object references
refs = model.get_references(surface)

# Check if a name is referenced
if model._references.is_referenced("MySchedule"):
    print("Schedule is in use")

# Get schedules actually used in the model
used = model.get_used_schedules()
```

### Adding and Removing Objects

```python
# Add a new object
zone = model.add("Zone", "NewZone", {
    "direction_of_relative_north": 0,
    "x_origin": 0,
    "y_origin": 0,
    "z_origin": 0,
})

# Remove an object
model.removeidfobject(zone)

# Copy an object with new name
new_zone = model.copyidfobject(zone, "CopiedZone")

# Rename (updates all references)
model.rename("Zone", "OldName", "NewName")
```

### Writing Files

```python
from eppy_plus import write_idf, write_epjson

# Write to IDF format
write_idf(model, "output.idf")

# Write to epJSON format
write_epjson(model, "output.epJSON")

# Get as string
idf_string = write_idf(model, None)
```

### Schema Access

```python
from eppy_plus import get_schema

# Get schema for a version
schema = get_schema((24, 1, 0))

# Check field info
field_names = schema.get_field_names("Zone")
is_ref = schema.is_reference_field("People", "zone_or_zonelist_name")
default = schema.get_field_default("Zone", "multiplier")
```

## Schema Files

eppy-plus uses the EpJSON schema (`Energy+.schema.epJSON`) as the single source of truth for:
- Field names and ordering
- Field types and defaults
- Reference relationships
- Validation rules

The package includes the schema for EnergyPlus 24.1.0. For other versions, the schema will be loaded from your EnergyPlus installation if available.

## License

MIT License - see LICENSE file for details.
