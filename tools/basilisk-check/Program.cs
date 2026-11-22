// basilisk-check: check UMI template libraries with Basilisk (research R15 of spec 003).
//
// For each library file, four checks run in order:
//   1. refs      the raw-JSON reference scan of research R1, which Basilisk does not do;
//   2. load      Basilisk's Library.FromJson;
//   3. orphans   Library.OrphanedComponents() is empty, every component reachable from a
//                template is in its collection, and Library.ToJson() succeeds;
//   4. complete  names non-null and unique per collection (glazing and gas materials together,
//                building templates too) and every required reference of research R3 non-null.
// See README.md for the command line, exit statuses and output format.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json;

using Basilisk.Core;

using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;

namespace BasiliskCheck
{
    internal sealed record Problem(int Check, string Message);

    internal static class Program
    {
        private const int StatusOk = 0;
        private const int StatusUsage = 2;
        private const int StatusCheckBase = 10;

        private static readonly string[] CheckNames = { "", "refs", "load", "orphans", "complete" };

        private const string Usage =
            "usage: basilisk-check [--report] [--no-unused] LIBRARY.json [LIBRARY.json ...]\n" +
            "       basilisk-check --list-fields\n";

        public static int Main(string[] args)
        {
            var files = new List<string>();
            bool report = false, noUnused = false, listFields = false;
            foreach (var arg in args)
            {
                switch (arg)
                {
                    case "--report": report = true; break;
                    case "--no-unused": noUnused = true; break;
                    case "--list-fields": listFields = true; break;
                    case "-h":
                    case "--help":
                        Console.Out.Write(Usage);
                        return StatusOk;
                    default:
                        if (arg.StartsWith("--", StringComparison.Ordinal))
                        {
                            Console.Error.Write($"basilisk-check: unknown option {arg}\n{Usage}");
                            return StatusUsage;
                        }
                        files.Add(arg);
                        break;
                }
            }

            if (listFields)
            {
                if (files.Count > 0 || report || noUnused)
                {
                    Console.Error.Write($"basilisk-check: --list-fields takes no other argument\n{Usage}");
                    return StatusUsage;
                }
                Console.Out.Write(FieldList.Render());
                return StatusOk;
            }
            if (files.Count == 0)
            {
                Console.Error.Write(Usage);
                return StatusUsage;
            }

            int status = StatusOk;
            foreach (var file in files)
            {
                string text;
                try
                {
                    // Detects and drops a UTF-8 byte order mark, as UMI does when it reads a file.
                    text = File.ReadAllText(file, Encoding.UTF8);
                }
                catch (Exception e) when (e is IOException or UnauthorizedAccessException)
                {
                    Console.Error.WriteLine($"basilisk-check: cannot read {file}: {e.Message}");
                    return StatusUsage;
                }

                var info = new List<string>();
                var problems = CheckLibrary(text, noUnused, info);
                if (problems.Count == 0)
                {
                    Console.Out.WriteLine($"ok {file}");
                }
                foreach (var p in problems)
                {
                    Console.Out.WriteLine($"fail {file}: check {p.Check} {CheckNames[p.Check]}: {p.Message}");
                }
                if (report)
                {
                    foreach (var line in info)
                    {
                        Console.Out.WriteLine($"info {file}: {line}");
                    }
                }
                if (problems.Count > 0 && status == StatusOk)
                {
                    status = StatusCheckBase + problems.Min(p => p.Check);
                }
            }
            return status;
        }

        internal static List<Problem> CheckLibrary(string text, bool noUnused, List<string> info)
        {
            var problems = new List<Problem>();
            problems.AddRange(RefScan.Run(text).Select(m => new Problem(1, m)));

            Library? lib;
            try
            {
                lib = Library.FromJson(text);
            }
            catch (Exception e)
            {
                problems.Add(new Problem(2, $"Library.FromJson failed: {OneLine(e.Message)}"));
                return problems;
            }
            if (lib is null)
            {
                problems.Add(new Problem(2, "Library.FromJson returned null"));
                return problems;
            }

            var graph = new Graph(lib);
            info.Add($"templates={lib.BuildingTemplates.Count} components={graph.CollectionMembers.Count} " +
                     $"null-references={graph.NullReferences.Count} unused={graph.Unused.Count} " +
                     $"orphaned={lib.OrphanedComponents().Count()}");
            foreach (var n in graph.NullReferences)
            {
                info.Add($"null reference after FromJson: {n}");
            }
            foreach (var u in graph.Unused)
            {
                info.Add($"unused component: {Describe(u)}");
            }

            // Check 3.
            List<LibraryComponent?> orphans;
            try
            {
                orphans = lib.OrphanedComponents().Cast<LibraryComponent?>().ToList();
            }
            catch (Exception e)
            {
                orphans = new List<LibraryComponent?>();
                problems.Add(new Problem(3, $"OrphanedComponents() failed: {OneLine(e.Message)}"));
            }
            foreach (var o in orphans)
            {
                info.Add($"OrphanedComponents() lists {Describe(o)}");
                problems.Add(new Problem(3, $"OrphanedComponents() lists {Describe(o)}"));
            }
            foreach (var (component, path) in graph.Missing)
            {
                problems.Add(new Problem(3, $"{Describe(component)} at {path} is not in {Graph.CollectionOf(component)}"));
            }
            if (noUnused)
            {
                foreach (var u in graph.Unused)
                {
                    problems.Add(new Problem(3, $"{Describe(u)} is not used by any building template"));
                }
            }
            try
            {
                lib.ToJson();
            }
            catch (Exception e)
            {
                problems.Add(new Problem(3, $"ToJson() failed: {OneLine(e.Message)}"));
            }

            // Check 4.
            problems.AddRange(Completeness.Run(lib).Select(m => new Problem(4, m)));
            return problems;
        }

        internal static string Describe(LibraryComponent? c) =>
            c is null ? "<null>" : $"{c.GetType().Name} \"{c.Name ?? "<null name>"}\"";

        internal static string OneLine(string s) => s.Replace("\r", " ").Replace("\n", " ");
    }

    /// <summary>Research R1's reference rules, applied to the raw JSON in file order.</summary>
    internal static class RefScan
    {
        public static List<string> Run(string text)
        {
            var problems = new List<string>();
            JsonDocument doc;
            try
            {
                doc = JsonDocument.Parse(text, new JsonDocumentOptions { AllowTrailingCommas = false });
            }
            catch (System.Text.Json.JsonException e)
            {
                problems.Add($"malformed JSON: {Program.OneLine(e.Message)}");
                return problems;
            }
            using (doc)
            {
                if (doc.RootElement.ValueKind != JsonValueKind.Object)
                {
                    problems.Add("the document is not a JSON object");
                    return problems;
                }
                var seen = new HashSet<string>(StringComparer.Ordinal);
                Walk(doc.RootElement, "", seen, problems);
            }
            return problems;
        }

        private static void Walk(JsonElement e, string pointer, HashSet<string> seen, List<string> problems)
        {
            switch (e.ValueKind)
            {
                case JsonValueKind.Object:
                    {
                        var props = e.EnumerateObject().ToList();
                        int index = 0;
                        bool hasRef = false;
                        foreach (var p in props)
                        {
                            var at = $"{pointer}/{Escape(p.Name)}";
                            if (p.Name == "$id")
                            {
                                if (index != 0)
                                {
                                    problems.Add($"{at}: \"$id\" is not the first key of its object");
                                }
                                if (p.Value.ValueKind != JsonValueKind.String)
                                {
                                    problems.Add($"{at}: \"$id\" is not a string");
                                }
                                else if (!seen.Add(p.Value.GetString()!))
                                {
                                    problems.Add($"{at}: duplicate \"$id\" \"{p.Value.GetString()}\"");
                                }
                            }
                            else if (p.Name == "$ref")
                            {
                                hasRef = true;
                                if (p.Value.ValueKind != JsonValueKind.String)
                                {
                                    problems.Add($"{at}: \"$ref\" is not a string");
                                }
                                else if (!seen.Contains(p.Value.GetString()!))
                                {
                                    problems.Add($"{at}: \"$ref\" \"{p.Value.GetString()}\" does not point to an \"$id\" defined earlier in the file");
                                }
                            }
                            else
                            {
                                Walk(p.Value, at, seen, problems);
                            }
                            index++;
                        }
                        if (hasRef && props.Count != 1)
                        {
                            problems.Add($"{pointer}: an object holding \"$ref\" has other keys");
                        }
                        break;
                    }
                case JsonValueKind.Array:
                    {
                        int i = 0;
                        foreach (var item in e.EnumerateArray())
                        {
                            Walk(item, $"{pointer}/{i}", seen, problems);
                            i++;
                        }
                        break;
                    }
                default:
                    break;
            }
        }

        private static string Escape(string key) => key.Replace("~", "~0").Replace("/", "~1");
    }

    /// <summary>What the loaded library references, by object identity.</summary>
    internal sealed class Graph
    {
        public readonly HashSet<LibraryComponent> CollectionMembers = new(ReferenceEqualityComparer.Instance);
        public readonly List<LibraryComponent> Unused = new();
        public readonly List<(LibraryComponent, string)> Missing = new();
        public readonly List<string> NullReferences = new();

        public Graph(Library lib)
        {
            foreach (var (name, items) in Collections(lib))
            {
                foreach (var c in items)
                {
                    if (c is not null) { CollectionMembers.Add(c); }
                }
            }

            // Every reference of every component, null or not, from the collections and from
            // whatever the templates reach.
            var reached = new HashSet<LibraryComponent>(ReferenceEqualityComparer.Instance);
            var visited = new HashSet<LibraryComponent>(ReferenceEqualityComparer.Instance);
            var stack = new Stack<(LibraryComponent, string)>();
            int t = 0;
            foreach (var template in lib.BuildingTemplates)
            {
                if (template is not null) { stack.Push((template, $"BuildingTemplates[{t}]")); }
                t++;
            }
            while (stack.Count > 0)
            {
                var (c, path) = stack.Pop();
                if (!visited.Add(c)) { continue; }
                reached.Add(c);
                if (!CollectionMembers.Contains(c)) { Missing.Add((c, path)); }
                foreach (var (key, child) in Children(c))
                {
                    if (child is not null) { stack.Push((child, $"{path}.{key}")); }
                }
            }
            foreach (var (name, items) in Collections(lib))
            {
                int i = 0;
                foreach (var c in items)
                {
                    if (c is null)
                    {
                        NullReferences.Add($"{name}[{i}]");
                    }
                    else
                    {
                        foreach (var (key, child) in Children(c))
                        {
                            if (child is null) { NullReferences.Add($"{name}[{i}] \"{c.Name}\".{key}"); }
                        }
                        if (!reached.Contains(c)) { Unused.Add(c); }
                    }
                    i++;
                }
            }
        }

        public static IEnumerable<(string, IEnumerable<LibraryComponent?>)> Collections(Library lib)
        {
            yield return ("GasMaterials", lib.GasMaterials);
            yield return ("GlazingMaterials", lib.GlazingMaterials);
            yield return ("OpaqueMaterials", lib.OpaqueMaterials);
            yield return ("OpaqueConstructions", lib.OpaqueConstructions);
            yield return ("WindowConstructions", lib.WindowConstructions);
            yield return ("StructureDefinitions", lib.StructureDefinitions);
            yield return ("DaySchedules", lib.DaySchedules);
            yield return ("WeekSchedules", lib.WeekSchedules);
            yield return ("YearSchedules", lib.YearSchedules);
            yield return ("DomesticHotWaterSettings", lib.DomesticHotWaterSettings);
            yield return ("VentilationSettings", lib.VentilationSettings);
            yield return ("ZoneConditionings", lib.ZoneConditionings);
            yield return ("ZoneConstructionSets", lib.ZoneConstructionSets);
            yield return ("ZoneLoads", lib.ZoneLoads);
            yield return ("Zones", lib.Zones);
            yield return ("BuildingTemplates", lib.BuildingTemplates);
            yield return ("WindowSettings", lib.WindowSettings);
        }

        public static string CollectionOf(LibraryComponent c) => c switch
        {
            GasMaterial => "GasMaterials",
            GlazingMaterial => "GlazingMaterials",
            OpaqueMaterial => "OpaqueMaterials",
            OpaqueConstruction => "OpaqueConstructions",
            WindowConstruction => "WindowConstructions",
            StructureInformation => "StructureDefinitions",
            DaySchedule => "DaySchedules",
            WeekSchedule => "WeekSchedules",
            YearSchedule => "YearSchedules",
            DomesticHotWaterSettings => "DomesticHotWaterSettings",
            ZoneVentilation => "VentilationSettings",
            ZoneConditioning => "ZoneConditionings",
            ZoneConstructions => "ZoneConstructionSets",
            ZoneLoads => "ZoneLoads",
            ZoneDefinition => "Zones",
            BuildingTemplate => "BuildingTemplates",
            WindowSettings => "WindowSettings",
            _ => "a collection",
        };

        /// <summary>Every reference a component holds, with its key, null included.</summary>
        public static IEnumerable<(string, LibraryComponent?)> Children(LibraryComponent c)
        {
            switch (c)
            {
                case BuildingTemplate b:
                    yield return ("Core", b.Core);
                    yield return ("Perimeter", b.Perimeter);
                    yield return ("Structure", b.Structure);
                    yield return ("Windows", b.Windows);
                    break;
                case ZoneDefinition z:
                    yield return ("Conditioning", z.Conditioning);
                    yield return ("Constructions", z.Constructions);
                    yield return ("DomesticHotWater", z.DomesticHotWater);
                    yield return ("InternalMassConstruction", z.InternalMassConstruction);
                    yield return ("Loads", z.Loads);
                    yield return ("Ventilation", z.Ventilation);
                    break;
                case ZoneConstructions zc:
                    yield return ("Facade", zc.Facade);
                    yield return ("Ground", zc.Ground);
                    yield return ("Partition", zc.Partition);
                    yield return ("Roof", zc.Roof);
                    yield return ("Slab", zc.Slab);
                    break;
                case ZoneLoads l:
                    yield return ("EquipmentAvailabilitySchedule", l.EquipmentAvailabilitySchedule);
                    yield return ("LightsAvailabilitySchedule", l.LightsAvailabilitySchedule);
                    yield return ("OccupancySchedule", l.OccupancySchedule);
                    break;
                case ZoneConditioning zcd:
                    yield return ("CoolingSchedule", zcd.CoolingSchedule);
                    yield return ("HeatingSchedule", zcd.HeatingSchedule);
                    yield return ("MechVentSchedule", zcd.MechVentSchedule);
                    break;
                case ZoneVentilation v:
                    yield return ("NatVentSchedule", v.NatVentSchedule);
                    yield return ("ScheduledVentilationSchedule", v.ScheduledVentilationSchedule);
                    break;
                case DomesticHotWaterSettings d:
                    yield return ("WaterSchedule", d.WaterSchedule);
                    break;
                case WindowSettings w:
                    yield return ("AfnWindowAvailability", w.AfnWindowAvailability);
                    yield return ("Construction", w.Construction);
                    yield return ("ShadingSystemAvailabilitySchedule", w.ShadingSystemAvailabilitySchedule);
                    yield return ("ZoneMixingAvailabilitySchedule", w.ZoneMixingAvailabilitySchedule);
                    break;
                case OpaqueConstruction oc:
                    for (int i = 0; i < oc.Layers.Count; i++)
                    {
                        yield return ($"Layers[{i}].Material", oc.Layers[i]?.Material);
                    }
                    break;
                case WindowConstruction wc:
                    for (int i = 0; i < wc.Layers.Count; i++)
                    {
                        yield return ($"Layers[{i}].Material", wc.Layers[i]?.Material);
                    }
                    break;
                case StructureInformation s:
                    int m = 0;
                    foreach (var ratio in s.MassRatios)
                    {
                        yield return ($"MassRatios[{m}].Material", ratio?.Material);
                        m++;
                    }
                    break;
                case YearSchedule y:
                    for (int i = 0; i < y.Parts.Count; i++)
                    {
                        yield return ($"Parts[{i}].Schedule", y.Parts[i]?.Schedule);
                    }
                    break;
                case WeekSchedule wk:
                    for (int i = 0; i < wk.Days.Length; i++)
                    {
                        yield return ($"Days[{i}]", wk.Days[i]);
                    }
                    break;
                default:
                    break;
            }
        }
    }

    /// <summary>Check 4: names (Basilisk's editor rules) and research R3's required references.</summary>
    internal static class Completeness
    {
        public static List<string> Run(Library lib)
        {
            var problems = new List<string>();

            // Names: non-null and unique per collection, glazing and gas materials together
            // (Controls/InterfaceModels/Library.cs builds one name dictionary per collection).
            void Names(string label, IEnumerable<(string, LibraryComponent?)> items)
            {
                var first = new Dictionary<string, string>(StringComparer.Ordinal);
                foreach (var (where, c) in items)
                {
                    if (c is null) { continue; }
                    if (c.Name is null)
                    {
                        problems.Add($"{where}: Name is null");
                    }
                    else if (first.TryGetValue(c.Name, out var earlier))
                    {
                        problems.Add($"{where}: name \"{c.Name}\" is already used by {earlier} ({label})");
                    }
                    else
                    {
                        first[c.Name] = where;
                    }
                }
            }
            static IEnumerable<(string, LibraryComponent?)> Indexed(string name, IEnumerable<LibraryComponent?> items) =>
                items.Select((c, i) => ($"{name}[{i}]", c));

            foreach (var (name, items) in Graph.Collections(lib))
            {
                if (name is "GlazingMaterials" or "GasMaterials") { continue; }
                Names(name, Indexed(name, items));
            }
            Names("GlazingMaterials and GasMaterials together",
                  Indexed("GlazingMaterials", lib.GlazingMaterials).Concat(Indexed("GasMaterials", lib.GasMaterials)));

            // Required references (research R3), and the shape of days, weeks and years.
            foreach (var (name, items) in Graph.Collections(lib))
            {
                int i = 0;
                foreach (var c in items)
                {
                    var where = $"{name}[{i}] \"{c?.Name}\"";
                    i++;
                    if (c is null)
                    {
                        problems.Add($"{name}[{i - 1}]: the entry is null");
                        continue;
                    }
                    foreach (var (key, child) in Graph.Children(c))
                    {
                        // Structure and its mass ratios are optional; everything else is required.
                        if (child is null && c is not StructureInformation && !(c is BuildingTemplate && key == "Structure"))
                        {
                            problems.Add($"{where}: {key} is null");
                        }
                    }
                    switch (c)
                    {
                        case DaySchedule d when d.Values is null || d.Values.Count != 24:
                            problems.Add($"{where}: Values has {d.Values?.Count ?? 0} entries, not 24");
                            break;
                        case WeekSchedule w when w.Days is null || w.Days.Length != 7:
                            problems.Add($"{where}: Days has {w.Days?.Length ?? 0} entries, not 7");
                            break;
                        case YearSchedule y:
                            problems.AddRange(YearCoverage(y).Select(m => $"{where}: {m}"));
                            break;
                        case OpaqueConstruction oc when oc.Layers.Count == 0:
                            problems.Add($"{where}: Layers is empty");
                            break;
                        case WindowConstruction wc when wc.Layers.Count == 0:
                            problems.Add($"{where}: Layers is empty");
                            break;
                        default:
                            break;
                    }
                }
            }
            return problems;
        }

        private static readonly int[] DaysInMonth = { 31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };

        private static int DayOfYear(int month, int day)
        {
            if (month < 1 || month > 12 || day < 1 || day > DaysInMonth[month - 1]) { return -1; }
            return DaysInMonth.Take(month - 1).Sum() + day;
        }

        /// <summary>Year parts cover 1 January to 31 December (a leap year) with no gap or overlap.</summary>
        private static IEnumerable<string> YearCoverage(YearSchedule y)
        {
            var spans = new List<(int From, int To, int Index)>();
            for (int i = 0; i < y.Parts.Count; i++)
            {
                var p = y.Parts[i];
                if (p is null) { yield return $"Parts[{i}] is null"; continue; }
                int from = DayOfYear(p.FromMonth, p.FromDay), to = DayOfYear(p.ToMonth, p.ToDay);
                if (from < 0 || to < 0)
                {
                    yield return $"Parts[{i}] has an invalid date ({p.FromMonth}/{p.FromDay} to {p.ToMonth}/{p.ToDay})";
                    continue;
                }
                if (to < from)
                {
                    yield return $"Parts[{i}] ends before it starts ({p.FromMonth}/{p.FromDay} to {p.ToMonth}/{p.ToDay})";
                    continue;
                }
                spans.Add((from, to, i));
            }
            if (spans.Count == 0)
            {
                yield return "Parts is empty";
                yield break;
            }
            spans.Sort((a, b) => a.From.CompareTo(b.From));
            int next = 1;
            foreach (var s in spans)
            {
                if (s.From > next) { yield return $"Parts leave a gap before Parts[{s.Index}] (days {next} to {s.From - 1})"; }
                if (s.From < next) { yield return $"Parts[{s.Index}] overlaps an earlier part"; }
                next = Math.Max(next, s.To + 1);
            }
            if (next <= 366) { yield return $"Parts end before 31 December (day {next - 1})"; }
        }
    }

    /// <summary>--list-fields: every serialised member of every Basilisk Core class.</summary>
    internal static class FieldList
    {
        public static string Render()
        {
            var resolver = new DefaultContractResolver();
            var assembly = typeof(Library).Assembly;
            var classes = assembly
                .GetTypes()
                .Where(t => t.IsClass && t.IsPublic && t.Namespace is not null
                            && t.Namespace.StartsWith("Basilisk.Core", StringComparison.Ordinal)
                            && !(t.IsAbstract && t.IsSealed) // static classes
                            && !typeof(Attribute).IsAssignableFrom(t))
                .ToList();

            var result = new SortedDictionary<string, List<string>>(StringComparer.Ordinal);
            foreach (var type in classes)
            {
                var closed = type.IsGenericTypeDefinition ? Close(type) : type;
                if (closed is null) { continue; }
                if (resolver.ResolveContract(closed) is not JsonObjectContract contract) { continue; }
                var keys = contract.Properties
                    .Where(p => !p.Ignored && p.Readable && Declares(type, p.DeclaringType))
                    .Select(p => p.PropertyName!)
                    .ToList();
                if (keys.Count == 0) { continue; }
                result[ClassName(type)] = keys;
            }

            var sb = new StringBuilder();
            sb.Append("{\n");
            int n = 0;
            foreach (var (cls, keys) in result)
            {
                sb.Append("  ").Append(JsonConvert.ToString(cls)).Append(": [");
                sb.Append(string.Join(", ", keys.Select(k => JsonConvert.ToString(k))));
                sb.Append(']');
                sb.Append(++n < result.Count ? ",\n" : "\n");
            }
            sb.Append("}\n");
            return sb.ToString();
        }

        private static bool Declares(Type type, Type? declaring)
        {
            if (declaring is null) { return false; }
            var d = declaring.IsGenericType ? declaring.GetGenericTypeDefinition() : declaring;
            return d == type;
        }

        private static Type? Close(Type generic)
        {
            // MaterialLayer<T> is the only generic class; close each parameter on its constraint.
            var args = generic.GetGenericArguments()
                .Select(a => a.GetGenericParameterConstraints().FirstOrDefault(c => c.IsClass) ?? typeof(object))
                .ToArray();
            try { return generic.MakeGenericType(args); }
            catch (ArgumentException) { return null; }
        }

        private static string ClassName(Type t)
        {
            var name = t.Name;
            int tick = name.IndexOf('`');
            return tick < 0 ? name : name[..tick];
        }
    }
}
