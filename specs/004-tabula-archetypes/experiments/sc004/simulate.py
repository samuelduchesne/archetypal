"""SC-004 experiment: one-zone EnergyPlus models from TABULA rows vs TABULA's seasonal method."""
from __future__ import annotations
import csv, json, math, subprocess, sys, sqlite3, collections
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

EP = "/usr/local/EnergyPlus-24-2-0/energyplus"
OUT = Path("/tmp/claude-0/sp/tabexp/runs")
EPW = json.load(open("/tmp/claude-0/sp/epw.json"))
ROWS = json.load(open("/tmp/claude-0/sp/buildings.json"))

def f(x, d=0.0):
    try:
        v = float(x); return v if math.isfinite(v) else d
    except (TypeError, ValueError):
        return d

AZ = {"East": 90, "South": 180, "West": 270, "North": 0}
FILM = {"roof": 0.14, "wall": 0.17, "floor": 0.21}

def rect(name, kind, cons, zone, area, az, tilt, bc="Outdoors", sun="SunExposed", wind="WindExposed"):
    # A square of the given area, at azimuth az (deg, outward normal) and tilt (0 roof, 90 wall, 180 floor)
    s = math.sqrt(max(area, 1e-4)); a = math.radians(az)
    ux, uy = math.cos(a), -math.sin(a)  # horizontal axis along the surface
    if tilt == 90:
        nx, ny = math.sin(a), math.cos(a)
        p0 = (100*nx, 100*ny)
        pts = [(p0[0], p0[1], s), (p0[0], p0[1], 0), (p0[0]+s*ux, p0[1]+s*uy, 0), (p0[0]+s*ux, p0[1]+s*uy, s)]
    elif tilt == 0:  # facing up, counter-clockwise seen from above
        pts = [(0, 0, 10), (s, 0, 10), (s, s, 10), (0, s, 10)]
    else:  # floor facing down
        pts = [(0, 0, 0), (0, s, 0), (s, s, 0), (s, 0, 0)]
    v = ",\n".join(f"  {x:.4f},{y:.4f},{z:.4f}" for x, y, z in pts)
    return f"BuildingSurface:Detailed,{name},{kind},{cons},{zone},,{bc},,{sun},{wind},autocalculate,4,\n{v};\n"

def model(r: dict, setpoint: float) -> str:
    A = f(r["A_C_Ref"]); h = f(r["h_room"], 2.5); vol = A * h
    t = [f"Version,24.2;\nTimestep,6;\nBuilding,b,0,Suburbs,0.04,0.4,MinimalShadowing,25,6;\n"
         "GlobalGeometryRules,UpperLeftCorner,Counterclockwise,World;\n"
         "SimulationControl,No,No,No,No,Yes,No,1;\nRunPeriod,y,1,1,,12,31,,Monday,No,No,No,Yes,Yes;\n"
         "ScheduleTypeLimits,any,,,Continuous;\n"
         f"Schedule:Constant,on,any,1;\nSchedule:Constant,sp,any,{setpoint:.4f};\nSchedule:Constant,ctl,any,1;\n"
         f"Zone,z,0,0,0,0,1,1,{h:.3f},{vol:.3f},{A:.3f};\n"
         "Material,conc,MediumRough,0.1,1.4,2300,900,0.9,0.7,0.7;\nConstruction,mass,conc;\n"]
    c_m = f(r["c_m"], 45) * 3600 * A  # J/K
    t.append(f"InternalMass,im,mass,z,,{c_m / (2300*900*0.1):.3f};\n")
    n = 0
    def opaque(kind, H, area, az, tilt, sun):
        nonlocal n
        if H <= 0 or area <= 0: return
        n += 1; U = H / area
        R = max(1 / U - FILM[kind], 0.01)
        t.append(f"Material:NoMass,m{n},Rough,{R:.5f},0.9,0.6,0.6;\nConstruction,c{n},m{n};\n")
        k = {"roof": "Roof", "wall": "Wall", "floor": "Floor"}[kind]
        t.append(rect(f"s{n}", k, f"c{n}", "z", area, az, tilt, sun="SunExposed" if sun else "NoSun", wind="WindExposed" if sun else "NoWind"))
    for i in (1, 2):
        b = f(r[f"b_Transmission_Roof_{i}"]); opaque("roof", f(r[f"H_Transmission_Roof_{i}"]), f(r[f"A_Calc_Roof_{i}"]), 0, 0, b >= 0.99)
    walls = [(f(r[f"H_Transmission_Wall_{i}"]), f(r[f"A_Calc_Wall_{i}"]), f(r[f"b_Transmission_Wall_{i}"])) for i in (1, 2, 3)]
    # Exposed walls: spread over the four orientations by their window areas (equal if none).
    win = {o: f(r[f"A_Calc_Window_{o}"]) for o in AZ}
    wsum = sum(win.values())
    for H, area, b in walls:
        if b >= 0.99:
            for o, az in AZ.items():
                share = win[o] / wsum if wsum > 0 else 0.25
                opaque("wall", H * share, area * share, az, 90, True)
        else:
            opaque("wall", H, area, 0, 90, False)
    for i in (1, 2):
        b = f(r[f"b_Transmission_Floor_{i}"]); opaque("floor", f(r[f"H_Transmission_Floor_{i}"]), f(r[f"A_Calc_Floor_{i}"]), 0, 180, False)
    opaque("wall", f(r["H_Transmission_Door_1"]), f(r["A_Calc_Door_1"]), 0, 90, False)
    opaque("wall", f(r["H_Transmission_ThermalBridging"]), max(f(r["H_Transmission_ThermalBridging"]), 1e-3), 0, 90, False)
    # Windows on near-adiabatic carrier walls.
    Uw = (f(r["H_Transmission_Window_1"]) + f(r["H_Transmission_Window_2"])) / max(f(r["A_Calc_Window_1"]) + f(r["A_Calc_Window_2"]), 1e-6)
    g = f(r["g_gl_n"]) * (1 - f(r["F_f"], 0.3))
    for o, az in list(AZ.items()) + [("Horizontal", None)]:
        Aw = f(r[f"A_Calc_Window_{o}"])
        if Aw <= 0: continue
        fsh = f(r["F_sh_hor"], 0.8) if o == "Horizontal" else f(r["F_sh_vert"], 0.6)
        n += 1
        t.append(f"Material:NoMass,mc{n},Rough,50,0.9,0.6,0.6;\nConstruction,cc{n},mc{n};\n")
        t.append(f"WindowMaterial:SimpleGlazingSystem,gl{n},{min(Uw,5.8):.4f},{min(g*fsh,0.95):.4f};\nConstruction,cw{n},gl{n};\n")
        tilt = 0 if o == "Horizontal" else 90
        t.append(rect(f"car{o}", "Roof" if tilt == 0 else "Wall", f"cc{n}", "z", Aw * 1.0005 + 0.01, az or 0, tilt))
        s = math.sqrt(Aw)
        if tilt == 90:
            a = math.radians(az); nx, ny = math.sin(a), math.cos(a); ux, uy = math.cos(a), -math.sin(a)
            S = math.sqrt(Aw * 1.0005 + 0.01); d = (S - s) / 2; p = (100*nx + d*ux, 100*ny + d*uy)
            pts = [(p[0], p[1], d + s), (p[0], p[1], d), (p[0]+s*ux, p[1]+s*uy, d), (p[0]+s*ux, p[1]+s*uy, d + s)]
        else:
            S = math.sqrt(Aw * 1.0005 + 0.01); d = (S - s) / 2
            pts = [(d, d, 10), (d+s, d, 10), (d+s, d+s, 10), (d, d+s, 10)]
        v = ",\n".join(f"  {x:.4f},{y:.4f},{z:.4f}" for x, y, z in pts)
        t.append(f"FenestrationSurface:Detailed,w{o},Window,cw{n},car{o},,autocalculate,,1,4,\n{v};\n")
    q = vol * (f(r["n_air_infiltration"]) + f(r["n_air_use"], 0.4)) / 3600
    t.append(f"ZoneInfiltration:DesignFlowRate,inf,z,on,Flow/Zone,{q:.6f},,,,1,0,0,0;\n")
    t.append(f"OtherEquipment,gains,None,z,on,EquipmentLevel,{f(r['phi_int'],3)*A:.3f},,,0,0.3,0;\n")
    t.append("ThermostatSetpoint:SingleHeating,th,sp;\nZoneControl:Thermostat,tc,z,ctl,ThermostatSetpoint:SingleHeating,th;\n"
             "ZoneHVAC:IdealLoadsAirSystem,il,,zin,,,50,13,0.0156,0.0077,NoLimit,,,NoLimit,,,,,ConstantSensibleHeatRatio,0.7,None;\n"
             "ZoneHVAC:EquipmentList,el,SequentialLoad,ZoneHVAC:IdealLoadsAirSystem,il,1,1,,;\n"
             "ZoneHVAC:EquipmentConnections,z,el,zin,,znode,zout;\n"
             "Output:Variable,*,Zone Ideal Loads Supply Air Sensible Heating Energy,Hourly;\n"
             "Output:Variable,*,Site Outdoor Air Drybulb Temperature,Hourly;\n"
             "Output:Variable,*,Surface Outside Face Incident Solar Radiation Rate per Area,Hourly;\n"
             "Output:SQLite,Simple;\n")
    return "".join(t)

def run(job):
    code, cc, sp, tag = job
    r = next(x for x in ROWS if x["Code_BuildingVariant"] == code)
    d = OUT / f"{code}_{tag}"; d.mkdir(parents=True, exist_ok=True)
    (d / "in.idf").write_text(model(r, sp))
    p = subprocess.run([EP, "-w", EPW[cc], "-d", str(d), str(d / "in.idf")], capture_output=True, text=True)
    sql = d / "eplusout.sql"
    if p.returncode or not sql.exists():
        return {"code": code, "tag": tag, "error": (d / "eplusout.err").read_text()[-800:] if (d / "eplusout.err").exists() else p.stderr[-500:]}
    con = sqlite3.connect(sql)
    def series(name, key=None):
        q = "select d.KeyValue, r.Value from ReportData r join ReportDataDictionary d using(ReportDataDictionaryIndex) join Time t using(TimeIndex) where d.Name=? and t.EnvironmentPeriodIndex=(select max(EnvironmentPeriodIndex) from EnvironmentPeriods) order by r.TimeIndex"
        out = collections.defaultdict(list)
        for k, v in con.execute(q, (name,)): out[k.upper()].append(v)
        return out
    heat = sum(series("Zone Ideal Loads Supply Air Sensible Heating Energy")["IL"]) / 3.6e6 / f(r["A_C_Ref"])
    tdb = series("Site Outdoor Air Drybulb Temperature")["ENVIRONMENT"]
    inc = series("Surface Outside Face Incident Solar Radiation Rate per Area")
    return {"code": code, "tag": tag, "cc": cc, "sp": sp, "q_ep": heat, "tdb": tdb,
            "inc": {k[3:]: v for k, v in inc.items() if k.startswith("CAR")}}

if __name__ == "__main__":
    jobs = json.load(open(sys.argv[1]))
    with ProcessPoolExecutor(int(sys.argv[3]) if len(sys.argv) > 3 else 2) as ex:
        res = list(ex.map(run, jobs))
    json.dump(res, open(sys.argv[2], "w"))
    print(sum("error" in x for x in res), "errors of", len(res))
