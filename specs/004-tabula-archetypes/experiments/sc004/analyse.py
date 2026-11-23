import json, math, statistics as st
rows = {r["Code_BuildingVariant"]: r for r in json.load(open("/tmp/claude-0/sp/buildings.json"))}
res = json.load(open("results.json"))
def f(x, d=0.0):
    try: return float(x)
    except: return d
def tabula(r, Te, HD, I, F):
    A = f(r["A_C_Ref"]); h_tr = f(r["h_Transmission"]); h_ve = f(r["h_Ventilation"]); ti = f(r["theta_i"], 20)
    q_ht = (h_tr + h_ve) * F * (ti - Te) * HD * 0.024
    g = f(r["g_gl_n"]); ff = f(r["F_f"], .3); fw = f(r["F_w"], .9)
    qs = sum((f(r["F_sh_hor"], .8) if o == "Horizontal" else f(r["F_sh_vert"], .6)) * (1-ff) * fw * g * f(r[f"A_Calc_Window_{o}"]) * I.get(o, 0) for o in ["Horizontal","East","South","West","North"]) / A
    qi = f(r["phi_int"], 3) * HD * 0.024
    tau = f(r["c_m"], 45) / (h_tr + h_ve); a = 0.8 + tau / 30
    gam = (qs + qi) / q_ht
    eta = (1 - gam**a) / (1 - gam**(a+1)) if abs(gam - 1) > 1e-9 else a / (a + 1)
    return q_ht - eta * (qs + qi)
errs = [x for x in res if "error" in x]
for e in errs: print("ERR", e["code"], e["tag"], e["error"][-200:].replace("\n"," "))
out = []
by = {}
for x in res:
    if "error" in x: continue
    by.setdefault(x["code"], {})[x["tag"]] = x
for code, d in by.items():
    r = rows[code]
    x = d.get("t20") or d.get("teff")
    tdb = x["tdb"]; days = [sum(tdb[i*24:(i+1)*24]) / 24 for i in range(365)]
    base = f(r["Theta_e_Base"], 12)
    hd = [i for i, v in enumerate(days) if v < base]
    Te = sum(days[i] for i in hd) / len(hd); HD = len(hd)
    I = {o.capitalize(): sum(sum(v[i*24:(i+1)*24]) for i in hd) / 1000 for o, v in x["inc"].items()}
    F = f(r["F_red_temp"], 1)
    rec = {"code": code, "cc": r["Code_Country"], "var": code[-1], "q_tab": f(r["q_h_nd"]),
           "q_tab_check": tabula(r, f(r["Theta_e"]), f(r["HeatingDays"]), {o: f(r[f"I_Sol_{o[:3] if o=='Horizontal' else o}"]) for o in ["Horizontal","East","South","West","North"]}, F),
           "q_tab_epw": tabula(r, Te, HD, I, F), "q_tab_epw_F1": tabula(r, Te, HD, I, 1.0),
           "q_ep20": d.get("t20", {}).get("q_ep"), "q_epeff": d.get("teff", {}).get("q_ep"),
           "Te_tab": f(r["Theta_e"]), "HD_tab": f(r["HeatingDays"]), "Te_epw": Te, "HD_epw": HD}
    out.append(rec)
json.dump(out, open("analysis.json", "w"), indent=1)
def rel(a, b): return a / b - 1
def summ(name, vals):
    v = [x for x in vals if x is not None]; a = [abs(x) for x in v]
    print(f"{name:44} n={len(v):3} median={st.median(v):+6.1%} mean|.|={st.mean(a):5.1%} p90|.|={sorted(a)[int(.9*len(a))-1]:5.1%} max|.|={max(a):5.1%}  within15={sum(x<=.15 for x in a)/len(a):4.0%} within25={sum(x<=.25 for x in a)/len(a):4.0%}")
print("check: own method reproduces TABULA:", max(abs(rel(o["q_tab_check"], o["q_tab"])) for o in out))
summ("climate: TABULA on EPW vs TABULA published", [rel(o["q_tab_epw"], o["q_tab"]) for o in out])
summ("method: EP teff vs TABULA on same EPW", [rel(o["q_epeff"], o["q_tab_epw"]) for o in out if o["q_epeff"]])
summ("method: EP 20C vs TABULA(F=1) on same EPW", [rel(o["q_ep20"], o["q_tab_epw_F1"]) for o in out if o["q_ep20"]])
summ("total SC-004: EP teff vs TABULA published", [rel(o["q_epeff"], o["q_tab"]) for o in out if o["q_epeff"]])
summ("total SC-004: EP 20C vs TABULA published", [rel(o["q_ep20"], o["q_tab"]) for o in out if o["q_ep20"]])
for v in "13":
    summ(f"  variant {v}: method EP teff vs TAB on EPW", [rel(o["q_epeff"], o["q_tab_epw"]) for o in out if o["q_epeff"] and o["var"] == v])
print()
for o in out:
    print(f'{o["code"]:36} TAB {o["q_tab"]:6.1f} TABepw {o["q_tab_epw"]:6.1f} EPeff {o["q_epeff"] or 0:6.1f} EP20 {o["q_ep20"] or 0:6.1f}  Te {o["Te_tab"]:4.1f}/{o["Te_epw"]:4.1f} HD {o["HD_tab"]:5.0f}/{o["HD_epw"]:3d}')
