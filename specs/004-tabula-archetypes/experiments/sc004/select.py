import json, re, collections
rows = json.load(open("/tmp/claude-0/sp/buildings.json"))
def f(x, d=0.0):
    try: return float(x)
    except: return d
ty = [r for r in rows if r.get("Code_StatusDataset") == "Typology" and f(r.get("q_h_nd")) > 0 and f(r.get("A_C_Ref")) > 0]
jobs = []; picked = []
for cc in ["DE", "FR", "IT", "SE", "GB", "PL", "AT"]:
    for size in ["SFH", "MFH"]:
        cands = [r for r in ty if r["Code_Country"] == cc and f".{size}." in r["Code_BuildingVariant"]]
        periods = sorted({r["Code_BuildingVariant"].split(".")[3] for r in cands})
        if not periods: continue
        for per in {periods[min(1, len(periods)-1)], periods[-2] if len(periods) > 2 else periods[-1]}:
            bs = [r for r in cands if r["Code_BuildingVariant"].split(".")[3] == per]
            base = sorted({r["Code_Building"] for r in bs})[0]
            for r in bs:
                if r["Code_Building"] == base and int(f(r["Number_BuildingVariant"])) in (1, 3):
                    te = f(r["Theta_e"]); ti = f(r["theta_i"], 20); F = f(r["F_red_temp"], 1)
                    picked.append(r["Code_BuildingVariant"])
                    jobs.append([r["Code_BuildingVariant"], cc, ti, "t20"])
                    jobs.append([r["Code_BuildingVariant"], cc, te + F * (ti - te), "teff"])
json.dump(jobs, open("jobs.json", "w")); print(len(picked), "buildings", len(jobs), "runs"); print(picked)
