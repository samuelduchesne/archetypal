# basilisk-check

Checks UMI template libraries with [Basilisk](https://github.com/MITSustainableDesignLab/basilisk),
the library UMI reads them with, and lists the fields Basilisk serialises (spec 003, research
R15 and R5). It is a contributor and CI tool: the archetypal package never needs .NET.

## Running it locally

You need git and the .NET 8 SDK.

```console
$ tools/basilisk-check/fetch-basilisk.sh
basilisk at 5cce24e8 in .../tools/basilisk-check/.basilisk
$ dotnet run --project tools/basilisk-check -- tests/fixtures/umi/*.json
ok tests/fixtures/umi/BostonTemplateLibrary_2.json
ok tests/fixtures/umi/BostonTemplateLibrary_nodup.json
ok tests/fixtures/umi/umi_samples_BostonTemplateLibrary.json
```

`fetch-basilisk.sh` clones Basilisk into `tools/basilisk-check/.basilisk/` and checks out
commit `5cce24e8` (tag `v0.2.2`); running it again only re-checks out the commit. The project
compiles Basilisk Core's C# sources from that checkout into a `net8.0` program, because Core
itself targets the end-of-life `net7`. The build stops with a message naming the script when
the checkout is missing. `.basilisk/`, `bin/` and `obj/` are ignored by git.

## Command line

```text
basilisk-check [--report] [--no-unused] LIBRARY.json [LIBRARY.json ...]
basilisk-check --list-fields
```

| Argument | Meaning |
|---|---|
| `LIBRARY.json` | A library file to check. Several may be given; each is checked. |
| `--report` | Also print `info` lines: counts, every reference that `Library.FromJson` left `null`, every unused component, every component `OrphanedComponents()` lists. They never change the exit status. |
| `--no-unused` | Fail check 3 on any component that no building template uses. Basilisk accepts such components (B2 and UZ have 29), but files written by archetypal must have none (contract `umi-file.md`, rule 3). Use it on written libraries, not on the samples. |
| `--list-fields` | Print the field list (below) and exit 0. Takes no other argument. |
| `-h`, `--help` | Print the usage and exit 0. |

### Checks

Each file goes through four checks, in order. A failing check does not stop the others,
except that checks 3 and 4 need check 2 to succeed.

1. **refs**: the raw-JSON reference scan of research R1, which Basilisk does not do. The file
   is a JSON object; every `$id` is a string, the first key of its object, and unique; every
   `$ref` is a string, alone in its object, and names an `$id` that appears earlier in the
   file.
2. **load**: `Library.FromJson` succeeds and returns a library.
3. **orphans**: `OrphanedComponents()` is empty; every component reachable from a building
   template is in its collection (Basilisk misses zone and structure definitions here); with
   `--no-unused`, every component is reachable from a template; `ToJson()` succeeds.
4. **complete**: names are non-null and unique per collection, glazing and gas materials
   together, building templates too; every required reference of research R3 is non-null
   (each layer's material, each week's days, each year part's week, a template's `Core`,
   `Perimeter` and `Windows`, the 6 references of a zone definition and the 5 of a
   construction set, every schedule of loads, conditioning, ventilation, hot water and window
   settings, the window settings' construction); every day has 24 values, every week 7 days,
   every construction at least one layer; each year's parts cover 1 January to 31 December
   (February has 29 days) without gap or overlap. A template's `Structure` may be null.

### Exit status

| Status | Meaning |
|---|---|
| 0 | Every file passed every check. |
| 2 | Usage error (no file, unknown option) or a file that cannot be read. Nothing more is checked. |
| 10 + N | A check failed: N is the lowest-numbered check that failed in the **first** failing file (11 refs, 12 load, 13 orphans, 14 complete). The other files are still checked and reported. |

### Output

On standard output, one line per result, in file order:

```text
ok <file>
fail <file>: check <N> <name>: <problem>
info <file>: <detail>                  (only with --report)
```

A file has either one `ok` line or one or more `fail` lines. Problems name where they are: a
JSON pointer for check 1 (`/ZoneLoads/0/OccupancySchedule/$ref`), the collection, index and
name for check 4 (`ZoneLoads[0] "Office loads": LightsAvailabilitySchedule is null`), and a
path from the template for check 3. Usage errors go to standard error.

## Field list (`--list-fields`)

Lists by reflection every member that Newtonsoft.Json serialises for every public class of
Basilisk Core, as one JSON object:

```json
{
  "BuildingTemplate": [
    "Core",
    "Lifespan",
    ...
  ],
  ...
}
```

- Classes are sorted by name (ordinal); keys are in serialisation order.
- Each key is listed under the class that declares it: `Name`, `Category`, `Comments` and
  `DataSource` under `LibraryComponent`, the shared material fields under `MaterialBase`, the
  assembly fields under `ConstructionBase`. A class that overrides a member lists it again:
  `Category` under `DaySchedule`, `WeekSchedule`, `YearSchedule` and `GasMaterial`, whose
  `Category` is fixed; `Layers` under `OpaqueConstruction` and `WindowConstruction`.
- `MaterialLayer<T>` is listed as `MaterialLayer`. `Library` lists the 17 collection keys.
  Classes that declare no serialised member (such as `WindowMaterialBase`) are left out.
- The output is ASCII with two-space indentation and a final newline, which is the layout of
  the `pretty-format-json` pre-commit hook, so the committed copy stays byte-identical.

The committed copy is `tests/data/basilisk_fields.json`; regenerate and compare it with

```console
$ dotnet run --project tools/basilisk-check -- --list-fields | diff - tests/data/basilisk_fields.json
```
