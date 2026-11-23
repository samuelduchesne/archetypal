import openpyxl, sys, json
wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
ws = wb["Calc.Set.Building"]
it = ws.iter_rows(values_only=True)
hdr = list(next(it))
rows = [dict(zip(hdr, r)) for r in it if r and r[0]]
print(len(rows), "rows")
json.dump(rows, open("/tmp/claude-0/sp/buildings.json", "w"), default=str)
ex = rows[0]; print({k: ex[k] for k in list(ex)[:12]})
