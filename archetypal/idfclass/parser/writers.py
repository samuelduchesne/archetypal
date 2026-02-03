"""
Writers for IDF and epJSON formats.

Provides serialization of IDFDocument to both formats.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO, TYPE_CHECKING

if TYPE_CHECKING:
    from .document import IDFDocument
    from .objects import IDFObject
    from .schema import EpJSONSchema


def write_idf(
    doc: "IDFDocument",
    filepath: Path | str | None = None,
    encoding: str = "latin-1",
) -> str | None:
    """
    Write document to IDF format.

    Args:
        doc: The document to write
        filepath: Output path (if None, returns string)
        encoding: Output encoding

    Returns:
        IDF string if filepath is None, otherwise None
    """
    writer = IDFWriter(doc)
    content = writer.to_string()

    if filepath:
        filepath = Path(filepath)
        with open(filepath, "w", encoding=encoding) as f:
            f.write(content)
        return None

    return content


def write_epjson(
    doc: "IDFDocument",
    filepath: Path | str | None = None,
    indent: int = 2,
) -> str | None:
    """
    Write document to epJSON format.

    Args:
        doc: The document to write
        filepath: Output path (if None, returns string)
        indent: JSON indentation

    Returns:
        JSON string if filepath is None, otherwise None
    """
    writer = EpJSONWriter(doc)
    data = writer.to_dict()

    if filepath:
        filepath = Path(filepath)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)
        return None

    return json.dumps(data, indent=indent)


class IDFWriter:
    """
    Writes IDFDocument to IDF text format.

    The IDF format is:
    ```
    ObjectType,
      field1,    !- Field 1 Name
      field2,    !- Field 2 Name
      field3;    !- Field 3 Name
    ```
    """

    def __init__(self, doc: "IDFDocument"):
        self._doc = doc

    def to_string(self) -> str:
        """Convert document to IDF string."""
        lines: list[str] = []

        # Write header comment
        lines.append("!-Generator archetypal")
        lines.append(f"!-Option SortedOrder")
        lines.append("")

        # Write Version first
        version = self._doc.version
        lines.append("Version,")
        lines.append(f"  {version[0]}.{version[1]};                    !- Version Identifier")
        lines.append("")

        # Write objects grouped by type
        for obj_type in sorted(self._doc._collections.keys()):
            collection = self._doc._collections[obj_type]
            if not collection:
                continue

            for obj in collection:
                obj_str = self._object_to_string(obj)
                lines.append(obj_str)
                lines.append("")

        return "\n".join(lines)

    def _object_to_string(self, obj: "IDFObject") -> str:
        """Convert a single object to IDF string."""
        lines: list[str] = []
        obj_type = obj._type
        schema = self._doc._schema

        # Get field order from schema or use data keys
        if obj._field_order:
            field_names = ["name"] + list(obj._field_order)
        elif schema:
            field_names = schema.get_all_field_names(obj_type)
        else:
            field_names = ["name"] + list(obj._data.keys())

        # Get field values
        values = []
        comments = []

        for field_name in field_names:
            if field_name == "name":
                values.append(obj.name or "")
                comments.append("Name")
            else:
                value = obj._data.get(field_name)
                values.append(self._format_value(value))
                # Convert field name to comment format
                comment = field_name.replace("_", " ").title()
                comments.append(comment)

        # Build output
        lines.append(f"{obj_type},")

        for i, (value, comment) in enumerate(zip(values, comments)):
            is_last = i == len(values) - 1
            terminator = ";" if is_last else ","

            # Format with comment
            field_str = f"  {value}{terminator}"
            field_str = field_str.ljust(30)
            field_str += f"!- {comment}"
            lines.append(field_str)

        return "\n".join(lines)

    def _format_value(self, value: Any) -> str:
        """Format a field value for IDF output."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, float):
            # Avoid scientific notation for small numbers
            if abs(value) < 1e-10:
                return "0"
            if abs(value) >= 1e10 or (abs(value) < 0.0001 and value != 0):
                return f"{value:.6e}"
            return f"{value:g}"
        if isinstance(value, list):
            # Handle vertex lists etc.
            return ", ".join(str(v) for v in value)
        return str(value)

    def write_to_file(self, filepath: Path | str, encoding: str = "latin-1") -> None:
        """Write to file."""
        content = self.to_string()
        with open(filepath, "w", encoding=encoding) as f:
            f.write(content)


class EpJSONWriter:
    """
    Writes IDFDocument to epJSON format.

    The epJSON format is:
    ```json
    {
      "Version": {
        "Version 1": {
          "version_identifier": "23.2"
        }
      },
      "Zone": {
        "Zone 1": {
          "direction_of_relative_north": 0.0,
          ...
        }
      }
    }
    ```
    """

    def __init__(self, doc: "IDFDocument"):
        self._doc = doc

    def to_dict(self) -> dict[str, Any]:
        """Convert document to epJSON dict."""
        result: dict[str, Any] = {}

        # Add Version
        version = self._doc.version
        result["Version"] = {
            "Version 1": {
                "version_identifier": f"{version[0]}.{version[1]}"
            }
        }

        # Add objects by type
        for obj_type, collection in self._doc._collections.items():
            if not collection:
                continue

            result[obj_type] = {}
            for obj in collection:
                obj_data = self._object_to_dict(obj)
                result[obj_type][obj.name] = obj_data

        return result

    def _object_to_dict(self, obj: "IDFObject") -> dict[str, Any]:
        """Convert object to epJSON dict (excluding name)."""
        result: dict[str, Any] = {}

        for field_name, value in obj._data.items():
            if value is not None:
                result[field_name] = self._format_value(value)

        return result

    def _format_value(self, value: Any) -> Any:
        """Format a field value for epJSON output."""
        # epJSON uses native JSON types
        if isinstance(value, str):
            # Check for special values
            lower = value.lower()
            if lower == "autocalculate":
                return "Autocalculate"
            if lower == "autosize":
                return "Autosize"
            if lower == "yes":
                return "Yes"
            if lower == "no":
                return "No"
        return value

    def write_to_file(self, filepath: Path | str, indent: int = 2) -> None:
        """Write to file."""
        data = self.to_dict()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)


def convert_idf_to_epjson(
    idf_path: Path | str,
    epjson_path: Path | str | None = None,
) -> Path:
    """
    Convert an IDF file to epJSON format.

    Args:
        idf_path: Input IDF file path
        epjson_path: Output epJSON path (default: same name with .epJSON extension)

    Returns:
        Path to the output file
    """
    from .idf_parser import parse_idf

    idf_path = Path(idf_path)

    if epjson_path is None:
        epjson_path = idf_path.with_suffix(".epJSON")
    else:
        epjson_path = Path(epjson_path)

    doc = parse_idf(idf_path)
    write_epjson(doc, epjson_path)

    return epjson_path


def convert_epjson_to_idf(
    epjson_path: Path | str,
    idf_path: Path | str | None = None,
) -> Path:
    """
    Convert an epJSON file to IDF format.

    Args:
        epjson_path: Input epJSON file path
        idf_path: Output IDF path (default: same name with .idf extension)

    Returns:
        Path to the output file
    """
    from .epjson_parser import parse_epjson

    epjson_path = Path(epjson_path)

    if idf_path is None:
        idf_path = epjson_path.with_suffix(".idf")
    else:
        idf_path = Path(idf_path)

    doc = parse_epjson(epjson_path)
    write_idf(doc, idf_path)

    return idf_path
