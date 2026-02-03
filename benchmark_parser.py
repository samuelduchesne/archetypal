#!/usr/bin/env python3
"""
Performance benchmark for archetypal v3 parser.

Compares the new parser against eppy to measure actual performance improvements.
"""

from __future__ import annotations

import gc
import importlib.util
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

# Load parser modules directly without going through archetypal package
PARSER_DIR = Path(__file__).parent / "archetypal" / "idfclass" / "parser"

def load_module(name: str, path: Path):
    """Load a module directly from file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

# Load modules in dependency order
exceptions_mod = load_module("parser.exceptions", PARSER_DIR / "exceptions.py")
objects_mod = load_module("parser.objects", PARSER_DIR / "objects.py")
references_mod = load_module("parser.references", PARSER_DIR / "references.py")
schema_mod = load_module("parser.schema", PARSER_DIR / "schema.py")
document_mod = load_module("parser.document", PARSER_DIR / "document.py")
idf_parser_mod = load_module("parser.idf_parser", PARSER_DIR / "idf_parser.py")
writers_mod = load_module("parser.writers", PARSER_DIR / "writers.py")

# Get the key classes and functions
parse_idf = idf_parser_mod.parse_idf
IDFDocument = document_mod.IDFDocument
IDFObject = objects_mod.IDFObject
IDFCollection = objects_mod.IDFCollection
write_idf = writers_mod.write_idf
write_epjson = writers_mod.write_epjson

# Try to import eppy for comparison
EPPY_AVAILABLE = False
IDD_PATH = None
try:
    from eppy.modeleditor import IDF

    # Find EnergyPlus IDD file
    idd_search_paths = [
        Path(__file__).parent / "Energy+.idd",
        "/usr/local/EnergyPlus-24-1-0/Energy+.idd",
        "/opt/EnergyPlus-24-1-0/Energy+.idd",
        Path.home() / "EnergyPlus-24-1-0" / "Energy+.idd",
    ]

    for idd_path in idd_search_paths:
        if Path(idd_path).exists():
            IDD_PATH = str(idd_path)
            IDF.setiddname(IDD_PATH)
            EPPY_AVAILABLE = True
            break
except ImportError:
    pass

if not EPPY_AVAILABLE:
    print("Note: eppy not available for comparison benchmarks")
    print("      Install eppy and place Energy+.idd in the project directory\n")


def generate_test_idf(num_zones: int = 100, surfaces_per_zone: int = 6) -> str:
    """Generate a test IDF file with specified complexity."""
    lines = [
        "Version, 24.1;",
        "",
        "Building,",
        "  TestBuilding,           !- Name",
        "  0.0,                     !- North Axis",
        "  City,                    !- Terrain",
        "  0.04,                    !- Loads Convergence Tolerance",
        "  0.4,                     !- Temperature Convergence Tolerance",
        "  FullInteriorAndExterior, !- Solar Distribution",
        "  25,                      !- Maximum Number of Warmup Days",
        "  6;                       !- Minimum Number of Warmup Days",
        "",
        "GlobalGeometryRules,",
        "  UpperLeftCorner,         !- Starting Vertex Position",
        "  Counterclockwise,        !- Vertex Entry Direction",
        "  Relative;                !- Coordinate System",
        "",
    ]

    # Add schedule type limits
    lines.extend([
        "ScheduleTypeLimits,",
        "  Fraction,                !- Name",
        "  0,                       !- Lower Limit",
        "  1,                       !- Upper Limit",
        "  Continuous;              !- Numeric Type",
        "",
    ])

    # Add schedules
    for i in range(20):
        lines.extend([
            f"Schedule:Constant,",
            f"  Schedule_{i},            !- Name",
            f"  Fraction,                !- Schedule Type Limits Name",
            f"  1.0;                     !- Hourly Value",
            "",
        ])

    # Add materials
    for i in range(10):
        lines.extend([
            f"Material,",
            f"  Material_{i},            !- Name",
            f"  Rough,                   !- Roughness",
            f"  0.{i+1},                 !- Thickness",
            f"  1.0,                     !- Conductivity",
            f"  2000,                    !- Density",
            f"  900;                     !- Specific Heat",
            "",
        ])

    # Add constructions
    for i in range(5):
        lines.extend([
            f"Construction,",
            f"  Construction_{i},        !- Name",
            f"  Material_{i};            !- Layer 1",
            "",
        ])

    # Add zones and surfaces
    for z in range(num_zones):
        x_offset = (z % 10) * 10
        y_offset = (z // 10) * 10

        lines.extend([
            f"Zone,",
            f"  Zone_{z},                !- Name",
            f"  0,                       !- Direction of Relative North",
            f"  {x_offset},              !- X Origin",
            f"  {y_offset},              !- Y Origin",
            f"  0,                       !- Z Origin",
            f"  1,                       !- Type",
            f"  1;                       !- Multiplier",
            "",
        ])

        # Add surfaces for this zone
        for s in range(surfaces_per_zone):
            surface_type = ["Floor", "Wall", "Wall", "Wall", "Wall", "Ceiling"][s % 6]
            lines.extend([
                f"BuildingSurface:Detailed,",
                f"  Surface_{z}_{s},         !- Name",
                f"  {surface_type},          !- Surface Type",
                f"  Construction_0,          !- Construction Name",
                f"  Zone_{z},                !- Zone Name",
                f"  ,                        !- Space Name",
                f"  Outdoors,                !- Outside Boundary Condition",
                f"  ,                        !- Outside Boundary Condition Object",
                f"  SunExposed,              !- Sun Exposure",
                f"  WindExposed,             !- Wind Exposure",
                f"  0.5,                     !- View Factor to Ground",
                f"  4,                       !- Number of Vertices",
                f"  0, 0, 0,                 !- Vertex 1",
                f"  10, 0, 0,                !- Vertex 2",
                f"  10, 10, 0,               !- Vertex 3",
                f"  0, 10, 0;                !- Vertex 4",
                "",
            ])

        # Add people, lights, equipment
        lines.extend([
            f"People,",
            f"  People_{z},              !- Name",
            f"  Zone_{z},                !- Zone Name",
            f"  Schedule_0,              !- Number of People Schedule Name",
            f"  People,                  !- Number of People Calculation Method",
            f"  10,                      !- Number of People",
            f"  ,                        !- People per Floor Area",
            f"  ,                        !- Floor Area per Person",
            f"  0.3,                     !- Fraction Radiant",
            f"  autocalculate,           !- Sensible Heat Fraction",
            f"  Schedule_1;              !- Activity Level Schedule Name",
            "",
            f"Lights,",
            f"  Lights_{z},              !- Name",
            f"  Zone_{z},                !- Zone Name",
            f"  Schedule_2,              !- Schedule Name",
            f"  Watts/Area,              !- Design Level Calculation Method",
            f"  ,                        !- Lighting Level",
            f"  10,                      !- Watts per Zone Floor Area",
            f"  ;                        !- Watts per Person",
            "",
        ])

    return "\n".join(lines)


def benchmark_eppy_parsing(idf_path: Path, iterations: int = 5) -> dict:
    """Benchmark eppy parsing speed."""
    if not EPPY_AVAILABLE:
        return {"error": "eppy not available"}

    times = []
    memory_peaks = []

    for _ in range(iterations):
        gc.collect()
        tracemalloc.start()

        start = time.perf_counter()
        idf = IDF(str(idf_path))
        end = time.perf_counter()

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        times.append(end - start)
        memory_peaks.append(peak / 1024 / 1024)  # MB

        del idf

    return {
        "mean_time_sec": statistics.mean(times),
        "std_time_sec": statistics.stdev(times) if len(times) > 1 else 0,
        "min_time_sec": min(times),
        "max_time_sec": max(times),
        "mean_memory_mb": statistics.mean(memory_peaks),
        "peak_memory_mb": max(memory_peaks),
    }


def benchmark_eppy_lookups(idf, iterations: int = 1000) -> dict:
    """Benchmark eppy object lookup speed."""
    if not EPPY_AVAILABLE:
        return {"error": "eppy not available"}

    import random

    # Get list of zone names
    zones = idf.idfobjects["ZONE"]
    zone_names = [z.Name for z in zones]

    # Benchmark zone lookup by name (eppy uses linear scan)
    start = time.perf_counter()
    for _ in range(iterations):
        name = random.choice(zone_names)
        # eppy lookup - must iterate to find by name
        for z in idf.idfobjects["ZONE"]:
            if z.Name == name:
                break
    zone_lookup_time = (time.perf_counter() - start) / iterations * 1_000_000  # microseconds

    # Benchmark iteration
    start = time.perf_counter()
    count = 0
    for obj_type in idf.idfobjects:
        for obj in idf.idfobjects[obj_type]:
            count += 1
    iteration_time = (time.perf_counter() - start) * 1000  # milliseconds

    return {
        "zone_lookup_us": zone_lookup_time,
        "iteration_time_ms": iteration_time,
        "total_objects": count,
    }


def benchmark_parsing(idf_content: str, iterations: int = 5) -> dict:
    """Benchmark parsing speed."""
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.idf', delete=False) as f:
        f.write(idf_content)
        temp_path = Path(f.name)

    times = []
    memory_peaks = []

    try:
        for _ in range(iterations):
            gc.collect()
            tracemalloc.start()

            start = time.perf_counter()
            doc = parse_idf(temp_path)
            end = time.perf_counter()

            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            times.append(end - start)
            memory_peaks.append(peak / 1024 / 1024)  # MB

            del doc
    finally:
        temp_path.unlink()

    return {
        "mean_time_sec": statistics.mean(times),
        "std_time_sec": statistics.stdev(times) if len(times) > 1 else 0,
        "min_time_sec": min(times),
        "max_time_sec": max(times),
        "mean_memory_mb": statistics.mean(memory_peaks),
        "peak_memory_mb": max(memory_peaks),
    }


def benchmark_lookups(doc, iterations: int = 1000) -> dict:
    """Benchmark object lookup speed."""
    import random

    # Get list of zone names
    zone_names = [z.name for z in doc["Zone"]]
    schedule_names = list(doc.schedules_dict.keys())

    # Benchmark zone lookup by name
    start = time.perf_counter()
    for _ in range(iterations):
        name = random.choice(zone_names)
        _ = doc["Zone"][name]
    zone_lookup_time = (time.perf_counter() - start) / iterations * 1_000_000  # microseconds

    # Benchmark schedule lookup
    start = time.perf_counter()
    for _ in range(iterations):
        name = random.choice(schedule_names)
        _ = doc.schedules_dict[name]
    schedule_lookup_time = (time.perf_counter() - start) / iterations * 1_000_000

    # Benchmark iteration
    start = time.perf_counter()
    count = 0
    for obj in doc.all_objects:
        count += 1
    iteration_time = (time.perf_counter() - start) * 1000  # milliseconds

    return {
        "zone_lookup_us": zone_lookup_time,
        "schedule_lookup_us": schedule_lookup_time,
        "iteration_time_ms": iteration_time,
        "total_objects": count,
    }


def benchmark_writing(doc, iterations: int = 3) -> dict:
    """Benchmark writing speed."""
    # IDF writing
    times_idf = []
    for _ in range(iterations):
        start = time.perf_counter()
        _ = write_idf(doc, None)
        times_idf.append(time.perf_counter() - start)

    # epJSON writing
    times_epjson = []
    for _ in range(iterations):
        start = time.perf_counter()
        _ = write_epjson(doc, None)
        times_epjson.append(time.perf_counter() - start)

    return {
        "idf_write_time_sec": statistics.mean(times_idf),
        "epjson_write_time_sec": statistics.mean(times_epjson),
    }


def benchmark_reference_graph(doc) -> dict:
    """Benchmark reference graph operations."""
    # Get a zone name to look up references
    zone_name = doc["Zone"][0].name if doc["Zone"] else None

    if not zone_name:
        return {"error": "No zones found"}

    # Benchmark get_referencing
    start = time.perf_counter()
    for _ in range(100):
        refs = doc.get_referencing(zone_name)
    ref_lookup_time = (time.perf_counter() - start) / 100 * 1_000_000  # microseconds

    # Benchmark get_used_schedules
    start = time.perf_counter()
    used = doc.get_used_schedules()
    used_schedules_time = (time.perf_counter() - start) * 1000  # milliseconds

    return {
        "reference_lookup_us": ref_lookup_time,
        "used_schedules_time_ms": used_schedules_time,
        "num_references_found": len(refs) if refs else 0,
        "num_used_schedules": len(used),
    }


def format_results(results: dict, title: str) -> str:
    """Format benchmark results as a table."""
    lines = [f"\n{'='*60}", f" {title}", f"{'='*60}"]

    for key, value in results.items():
        if isinstance(value, float):
            lines.append(f"  {key}: {value:.4f}")
        else:
            lines.append(f"  {key}: {value}")

    return "\n".join(lines)


def main():
    """Run all benchmarks."""
    print("=" * 60)
    print(" Archetypal v3 Parser Performance Benchmark")
    print("=" * 60)

    # Test different model sizes
    sizes = [
        (10, 6, "Small (10 zones, 60 surfaces)"),
        (100, 6, "Medium (100 zones, 600 surfaces)"),
        (500, 6, "Large (500 zones, 3000 surfaces)"),
    ]

    all_results = []
    eppy_results = []

    for num_zones, surfaces_per_zone, description in sizes:
        print(f"\n\n{'#'*60}")
        print(f" Model Size: {description}")
        print(f"{'#'*60}")

        # Generate test IDF
        print("\nGenerating test IDF...")
        idf_content = generate_test_idf(num_zones, surfaces_per_zone)
        file_size_kb = len(idf_content.encode()) / 1024
        num_lines = idf_content.count('\n')
        print(f"  File size: {file_size_kb:.1f} KB")
        print(f"  Lines: {num_lines}")

        # Write to temp file for both parsers
        with tempfile.NamedTemporaryFile(mode='w', suffix='.idf', delete=False) as f:
            f.write(idf_content)
            temp_path = Path(f.name)

        try:
            # ===== NEW PARSER BENCHMARKS =====
            print("\n--- New Parser (v3) ---")

            # Run parsing benchmark
            print("\nBenchmarking parsing...")
            parse_results = benchmark_parsing(idf_content, iterations=5)
            print(format_results(parse_results, "Parsing Results"))

            doc = parse_idf(temp_path)

            # Run lookup benchmark
            print("\nBenchmarking lookups...")
            lookup_results = benchmark_lookups(doc, iterations=1000)
            print(format_results(lookup_results, "Lookup Results"))

            # Run reference graph benchmark
            print("\nBenchmarking reference graph...")
            ref_results = benchmark_reference_graph(doc)
            print(format_results(ref_results, "Reference Graph Results"))

            # Run writing benchmark
            print("\nBenchmarking writing...")
            write_results = benchmark_writing(doc, iterations=3)
            print(format_results(write_results, "Writing Results"))

            all_results.append({
                "description": description,
                "file_size_kb": file_size_kb,
                "num_objects": lookup_results["total_objects"],
                **parse_results,
                **lookup_results,
                **ref_results,
                **write_results,
            })

            # ===== EPPY BENCHMARKS =====
            if EPPY_AVAILABLE:
                print("\n--- eppy (v2) ---")

                # Run eppy parsing benchmark
                print("\nBenchmarking eppy parsing...")
                eppy_parse = benchmark_eppy_parsing(temp_path, iterations=5)
                if "error" not in eppy_parse:
                    print(format_results(eppy_parse, "eppy Parsing Results"))

                    # Run eppy lookup benchmark
                    print("\nBenchmarking eppy lookups...")
                    idf = IDF(str(temp_path))
                    eppy_lookup = benchmark_eppy_lookups(idf, iterations=1000)
                    print(format_results(eppy_lookup, "eppy Lookup Results"))

                    eppy_results.append({
                        "description": description,
                        **eppy_parse,
                        **eppy_lookup,
                    })

        finally:
            temp_path.unlink()

    # Summary table
    print("\n\n" + "=" * 80)
    print(" PERFORMANCE SUMMARY - New Parser (v3)")
    print("=" * 80)
    print(f"\n{'Model':<40} {'Parse (s)':<12} {'Memory (MB)':<12} {'Lookup (us)':<12}")
    print("-" * 80)
    for r in all_results:
        print(f"{r['description']:<40} {r['mean_time_sec']:<12.4f} {r['mean_memory_mb']:<12.2f} {r['zone_lookup_us']:<12.2f}")

    # Comparison table if eppy is available
    if eppy_results:
        print("\n\n" + "=" * 100)
        print(" COMPARISON: New Parser vs eppy")
        print("=" * 100)
        print(f"\n{'Model':<35} {'v3 (s)':<10} {'eppy (s)':<10} {'Speedup':<12} {'v3 (us)':<10} {'eppy (us)':<12} {'Speedup':<10}")
        print("-" * 100)
        for v3, eppy in zip(all_results, eppy_results):
            parse_speedup = eppy['mean_time_sec'] / v3['mean_time_sec'] if v3['mean_time_sec'] > 0 else 0
            lookup_speedup = eppy['zone_lookup_us'] / v3['zone_lookup_us'] if v3['zone_lookup_us'] > 0 else 0
            print(f"{v3['description']:<35} {v3['mean_time_sec']:<10.3f} {eppy['mean_time_sec']:<10.3f} {parse_speedup:>6.1f}x      {v3['zone_lookup_us']:<10.2f} {eppy['zone_lookup_us']:<12.2f} {lookup_speedup:>6.0f}x")
    else:
        print("\n\n" + "=" * 80)
        print(" EPPY COMPARISON NOT AVAILABLE")
        print("=" * 80)
        print("\nTo enable comparison, install eppy and EnergyPlus:")
        print("  pip install eppy")
        print("  # Then ensure Energy+.idd is available")

    print("\n" + "=" * 80)
    print(" KEY FEATURES")
    print("=" * 80)
    print("""
  - Streaming parser with memory mapping for large files
  - O(1) hash-based lookups by object name
  - Reference graph for instant dependency queries
  - Lean IDFObject with __slots__ for memory efficiency
  - EpJSON schema as single source of truth
""")


if __name__ == "__main__":
    main()
