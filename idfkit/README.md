# idfkit

A fast, modern EnergyPlus IDF/epJSON parser for Python.

## Features

- **High-performance parsing** of IDF and epJSON files with streaming support
- **O(1) lookups** by object name via indexed collections
- **Reference graph** for instant dependency tracking between objects
- **Schema-driven** using EpJSON schema as the single source of truth
- **On-demand validation** against EpJSON schema
- **Zero dependencies** - pure Python, no external packages required
- **Memory efficient** - `__slots__`-based objects (~200 bytes each)
- **Type-safe** - full type annotations with `py.typed` marker

## Installation

```bash
pip install idfkit
```

## Quick Start

```python
from idfkit import load_idf, new_document

# Load an existing IDF file
model = load_idf("building.idf")

# Access objects with O(1) lookup
zone = model["Zone"]["MyZone"]
print(zone.x_origin)

# Find all objects that reference a zone
surfaces = model.get_referencing("MyZone")

# Create a new document
model = new_document(version=(24, 1, 0))
model.add("Zone", "NewZone", {"x_origin": 0, "y_origin": 0})

# Write to file
from idfkit import write_idf
write_idf(model, "output.idf")
```

## License

MIT
