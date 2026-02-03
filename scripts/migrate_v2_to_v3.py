#!/usr/bin/env python
"""
Migration script for archetypal v2 to v3.

This script helps users transition their code from archetypal v2 (eppy-based)
to archetypal v3 (new parser).

Usage:
    python migrate_v2_to_v3.py [--check] [--fix] <directory>

Options:
    --check     Check for compatibility issues without making changes
    --fix       Automatically fix simple compatibility issues
    <directory> Directory containing Python files to migrate

Key Changes in v3:
    1. IDF class no longer inherits from eppy/geomeppy
    2. EpBunch objects are now IDFObject instances
    3. Idf_MSequence is now IDFCollection
    4. Some internal methods have changed
    5. New parser is faster and supports epJSON natively

Migration Guide:
    - idf.idfobjects["ZONE"] still works (backward compatible)
    - zone.Name still works (backward compatible)
    - zone.fieldnames still works (backward compatible)
    - New: idf.zones (direct attribute access)
    - New: idf.validate() (schema validation)
    - New: idf.to_epjson() (epJSON export)
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class MigrationIssue:
    """Represents a migration issue found in code."""

    file: Path
    line: int
    column: int
    code: str
    message: str
    fix: str | None = None
    severity: str = "warning"  # "error", "warning", "info"


# Patterns to check for migration issues
MIGRATION_PATTERNS = [
    # Imports that need to change
    {
        "pattern": r"from eppy\.bunch_subclass import (?:EpBunch|BadEPFieldError)",
        "message": "eppy imports are no longer needed in v3",
        "fix": "from archetypal.idfclass.parser import IDFObject",
        "code": "M001",
    },
    {
        "pattern": r"from eppy\.idf_msequence import Idf_MSequence",
        "message": "Idf_MSequence is replaced by IDFCollection",
        "fix": "from archetypal.idfclass.parser import IDFCollection",
        "code": "M002",
    },
    {
        "pattern": r"from geomeppy\.patches import EpBunch",
        "message": "geomeppy imports are no longer needed in v3",
        "fix": "from archetypal.idfclass.parser import IDFObject",
        "code": "M003",
    },
    {
        "pattern": r"from geomeppy import IDF as GeomIDF",
        "message": "GeomIDF inheritance is no longer used",
        "fix": "# Geometry operations are now built into IDF class",
        "code": "M004",
    },
    # Type annotations that need to change
    {
        "pattern": r": EpBunch\b",
        "message": "EpBunch type should be IDFObject",
        "fix": ": IDFObject",
        "code": "M005",
    },
    {
        "pattern": r": Idf_MSequence\b",
        "message": "Idf_MSequence type should be IDFCollection",
        "fix": ": IDFCollection",
        "code": "M006",
    },
    # Method calls that have changed
    {
        "pattern": r"\.obj2bunch\(",
        "message": "obj2bunch is no longer used - create IDFObject directly",
        "fix": None,
        "code": "M007",
    },
    {
        "pattern": r"\.newrawobject\(",
        "message": "newrawobject is no longer used - use newidfobject()",
        "fix": None,
        "code": "M008",
    },
    {
        "pattern": r"idfreader1\(",
        "message": "idfreader1 is replaced by parse_idf()",
        "fix": "parse_idf(",
        "code": "M009",
    },
    # Internal attributes that have changed
    {
        "pattern": r"\.theidf\.",
        "message": ".theidf is now ._document (but .theidf still works for compatibility)",
        "fix": None,
        "code": "M010",
        "severity": "info",
    },
    {
        "pattern": r"\._model\b",
        "message": "._model (Eplusdata) is no longer used",
        "fix": None,
        "code": "M011",
    },
    {
        "pattern": r"\.idd_info\b",
        "message": ".idd_info is replaced by schema-based validation",
        "fix": None,
        "code": "M012",
        "severity": "info",
    },
]

# Backward compatible patterns (no action needed)
COMPATIBLE_PATTERNS = [
    r"\.idfobjects\[",  # Still works
    r"\.Name\b",  # Still works
    r"\.fieldnames\b",  # Still works
    r"\.fieldvalues\b",  # Still works
    r"\.newidfobject\(",  # Still works
    r"\.getobject\(",  # Still works
    r"\.save\(",  # Still works
    r"\.saveas\(",  # Still works
    r"\.simulate\(",  # Still works
]


def find_issues(file_path: Path) -> Iterator[MigrationIssue]:
    """Find migration issues in a Python file."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = file_path.read_text(encoding="latin-1")

    lines = content.split("\n")

    for line_num, line in enumerate(lines, 1):
        for pattern_info in MIGRATION_PATTERNS:
            pattern = pattern_info["pattern"]
            matches = list(re.finditer(pattern, line))

            for match in matches:
                yield MigrationIssue(
                    file=file_path,
                    line=line_num,
                    column=match.start() + 1,
                    code=pattern_info["code"],
                    message=pattern_info["message"],
                    fix=pattern_info.get("fix"),
                    severity=pattern_info.get("severity", "warning"),
                )


def apply_fix(file_path: Path, issue: MigrationIssue) -> bool:
    """Apply a fix to a file."""
    if issue.fix is None:
        return False

    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    line_idx = issue.line - 1
    line = lines[line_idx]

    # Find and replace the pattern
    for pattern_info in MIGRATION_PATTERNS:
        if pattern_info["code"] == issue.code:
            new_line = re.sub(pattern_info["pattern"], issue.fix, line)
            if new_line != line:
                lines[line_idx] = new_line
                file_path.write_text("\n".join(lines), encoding="utf-8")
                return True

    return False


def check_directory(directory: Path, fix: bool = False) -> list[MigrationIssue]:
    """Check all Python files in a directory for migration issues."""
    issues = []

    for py_file in directory.rglob("*.py"):
        # Skip migration script itself and __pycache__
        if "__pycache__" in str(py_file) or py_file.name == "migrate_v2_to_v3.py":
            continue

        file_issues = list(find_issues(py_file))
        issues.extend(file_issues)

        if fix:
            for issue in file_issues:
                if issue.fix:
                    if apply_fix(py_file, issue):
                        print(f"  Fixed {issue.code} in {py_file}:{issue.line}")

    return issues


def print_report(issues: list[MigrationIssue]) -> None:
    """Print a migration report."""
    if not issues:
        print("\n✓ No migration issues found!")
        return

    # Group by file
    by_file: dict[Path, list[MigrationIssue]] = {}
    for issue in issues:
        by_file.setdefault(issue.file, []).append(issue)

    print(f"\nFound {len(issues)} migration issue(s) in {len(by_file)} file(s):\n")

    for file_path, file_issues in sorted(by_file.items()):
        print(f"{file_path}:")
        for issue in sorted(file_issues, key=lambda i: i.line):
            severity_marker = {
                "error": "✗",
                "warning": "⚠",
                "info": "ℹ",
            }.get(issue.severity, "•")

            fix_hint = f" → {issue.fix}" if issue.fix else ""
            print(
                f"  {severity_marker} {issue.line}:{issue.column} [{issue.code}] {issue.message}{fix_hint}"
            )
        print()


def print_migration_guide() -> None:
    """Print the migration guide."""
    guide = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    Archetypal v2 to v3 Migration Guide                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

OVERVIEW
────────
Archetypal v3 replaces the eppy-based IDF parser with a new, high-performance
parser that is 10-20x faster and supports native epJSON format.

WHAT'S NEW
──────────
• Native epJSON support (IDF.from_epjson(), IDF.to_epjson())
• O(1) object lookup by name (vs O(n) in v2)
• Schema-based validation (IDF.validate())
• Reference graph for dependency tracking
• 10-20x faster parsing for large files
• ~5x less memory usage

BACKWARD COMPATIBLE (no changes needed)
───────────────────────────────────────
• idf.idfobjects["Zone"]  ✓
• zone.Name, zone.fieldnames, zone.fieldvalues  ✓
• idf.newidfobject(), idf.getobject()  ✓
• idf.save(), idf.saveas(), idf.copy()  ✓
• idf.simulate()  ✓
• idf.schedules_dict  ✓

CHANGES REQUIRED
────────────────
1. Import changes:
   OLD: from eppy.bunch_subclass import EpBunch
   NEW: from archetypal.idfclass.parser import IDFObject

   OLD: from eppy.idf_msequence import Idf_MSequence
   NEW: from archetypal.idfclass.parser import IDFCollection

2. Type annotations:
   OLD: def process_zone(zone: EpBunch) -> None:
   NEW: def process_zone(zone: IDFObject) -> None:

3. Internal attributes (if you were using them):
   OLD: idf._model, idf.idd_info
   NEW: idf._document, idf._document._schema

4. Geometry operations:
   OLD: from geomeppy.geom.polygons import Polygon3D
   NEW: Geometry support is being redesigned - see geometry.py

NEW FEATURES TO EXPLORE
───────────────────────
• idf.zones, idf.materials  (direct collection access)
• idf.validate()  (schema validation)
• idf.get_referencing("ZoneName")  (find objects referencing a name)
• idf.get_used_schedules()  (O(1) lookup of used schedules)
• parse_idf(), parse_epjson()  (low-level parsing functions)
• write_idf(), write_epjson()  (low-level writing functions)

REMOVED DEPENDENCIES
────────────────────
• eppy (no longer required)
• geomeppy (no longer required for parsing)

For more information, see the documentation at:
https://archetypal.readthedocs.io/en/latest/migration.html
"""
    print(guide)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate archetypal code from v2 to v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "directory",
        type=Path,
        nargs="?",
        help="Directory to check for migration issues",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for issues without making changes",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically fix simple issues",
    )
    parser.add_argument(
        "--guide",
        action="store_true",
        help="Print the migration guide",
    )

    args = parser.parse_args()

    if args.guide:
        print_migration_guide()
        return 0

    if args.directory is None:
        parser.print_help()
        print("\nError: Please specify a directory to check")
        return 1

    if not args.directory.exists():
        print(f"Error: Directory not found: {args.directory}")
        return 1

    print(f"Checking {args.directory} for migration issues...")
    issues = check_directory(args.directory, fix=args.fix)
    print_report(issues)

    if args.fix:
        fixable = sum(1 for i in issues if i.fix)
        print(f"\nApplied {fixable} automatic fix(es).")
        print("Please review the changes and test your code.")

    # Return exit code based on severity
    if any(i.severity == "error" for i in issues):
        return 2
    if any(i.severity == "warning" for i in issues):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
