import json
# ---------- INPUTS (every one is tagged in the report's assumptions register) ----------
BUA = {"A_174k":174000, "B_263k":263020, "C_437k":263020+174000}   # m2 ; contractor-documented, NOT verified campus total
EUI = {"low":130, "mid":165, "high":215}                           # kWh/m2/yr electricity, hot-climate educational range
CTRL = {"cons":0.50, "mod":0.60, "high":0.70}                      # controllable share of total electricity
COV  = {"cons":0.50, "mod":0.70, "high":0.90}                      # share of controllable load under system control
SAV  = {"cons":0.10, "mod":0.18, "high":0.28}                      # saving on controlled loads
TARIFF = 2.55   # EGP/kWh EgyptERA Apr-2026, medium voltage 'other users' (excl. stamp/service fees)
TARIFF_LV = 2.74
EF = 0.563      # kgCO2/kWh Ember 2024/25 (lifecycle basis, secondary access)
out = {"inputs":dict(BUA=BUA,EUI=EUI,CTRL=CTRL,COV=COV,SAV=SAV,TARIFF=TARIFF,EF=EF)}
base_central = BUA["B_263k"]*EUI["mid"]
out["baseline_matrix_kWh"] = {b:{e:BUA[b]*EUI[e] for e in EUI} for b in BUA}
sc = {}
for s in ["cons","mod","high"]:
    ctrl_kwh = base_central*CTRL[s]
    covered = ctrl_kwh*COV[s]
    saved = covered*SAV[s]
    sc[s] = dict(baseline=base_central, controllable=ctrl_kwh, covered=covered, saving_on_controlled=SAV[s],
        saved_annual=saved, saved_pct_total=saved/base_central, saved_pct_controllable=saved/ctrl_kwh,
        saved_month=saved/12, saved_5y=saved*5, egp_year=saved*TARIFF, egp_5y=saved*TARIFF*5,
        egp_year_lv=saved*TARIFF_LV, t_co2_year=saved*EF/1000, t_co2_5y=saved*EF/1000*5,
        projected=base_central-saved)
out["scenarios"]=sc
# sensitivity: moderate savings fraction across BUA x EUI
sens={}
for b in BUA:
    sens[b]={}
    for e in EUI:
        base=BUA[b]*EUI[e]
        sens[b][e]={s: base*CTRL[s]*COV[s]*SAV[s] for s in sc}
out["sensitivity_saved_kWh"]=sens
# building categories (central BUA/EUI). area shares = scenario assumption (not verified)
cats = {
 "Academic / classrooms": dict(share=0.40, ctrl=0.65, rate=dict(cons=0.10,mod=0.18,high=0.28)),
 "Laboratories (teaching)": dict(share=0.10, ctrl=0.40, rate=dict(cons=0.05,mod=0.10,high=0.20)),
 "Admin / library / services": dict(share=0.15, ctrl=0.65, rate=dict(cons=0.08,mod=0.15,high=0.23)),
 "Dormitories / housing": dict(share=0.25, ctrl=0.60, rate=dict(cons=0.10,mod=0.18,high=0.28)),
 "Sports / hospital / other": dict(share=0.10, ctrl=0.40, rate=dict(cons=0.05,mod=0.10,high=0.15)),
}
cat_out={}
tot={s:0 for s in sc}
for n,c in cats.items():
    area=BUA["B_263k"]*c["share"]; base=area*EUI["mid"]
    d=dict(share=c["share"],area=area,baseline=base,ctrl=c["ctrl"],controllable=base*c["ctrl"],rate=c["rate"])
    for s in sc:
        v=base*c["ctrl"]*COV[s]*c["rate"][s]; d["saved_"+s]=v; tot[s]+=v
    cat_out[n]=d
out["categories"]=cat_out; out["category_totals"]=tot
out["category_totals_pct"]={s:tot[s]/base_central for s in tot}
json.dump(out,open("model.json","w"),indent=1)
for s,v in sc.items():
    print(s, {k:(round(x,3) if isinstance(x,float) and x<10 else round(x)) for k,x in v.items()})
print("bottom-up", {s:round(t) for s,t in tot.items()}, {s:round(t/base_central,4) for s,t in tot.items()})
print({b:{e:round(v/1e6,1) for e,v in d.items()} for b,d in out["baseline_matrix_kWh"].items()})
print({b:{e:{s:round(x/1e3) for s,x in d2.items()} for e,d2 in d.items()} for b,d in sens.items()})
