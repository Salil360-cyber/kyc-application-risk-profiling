"""Builds docs/index.html, the interactive version of the risk model.
Reads the rules from the workbook, packs the 30,000 applications into a compact JSON,
checks that the default rules reproduce the workbook's tier counts, and writes the page."""
import json, math
from pathlib import Path
import openpyxl
import pandas as pd

WB = "KYC_Risk_Profiling_Solved.xlsx"
ws = openpyxl.load_workbook(WB, data_only=True)["Ref_Rules"]
rules, tiers, last_dev = {}, {}, None
for r in ws.iter_rows(values_only=True):
    if r[0] and str(r[0]).startswith("F") and len(str(r[0])) == 2:
        rules[r[0]] = {"name": r[1], "thr": r[4], "pts": r[5]}
    elif r[0] in ("Low", "Medium", "High", "Critical"):
        tiers[r[0]] = {"min": r[1], "action": r[2]}
    elif r[0] == "Last development month":
        last_dev = r[1]

d = pd.read_csv("BAF_Sample_30k.csv")
# booleans packed into bits: 1 both phones invalid, 2 windows, 4 foreign, 8 no keep-alive, 16 free email, 32 fraud
bits = (((d.phone_home_valid == 0) & (d.phone_mobile_valid == 0)).astype(int) * 1
        + (d.device_os == "windows").astype(int) * 2 + (d.foreign_request == 1).astype(int) * 4
        + (d.keep_alive_session == 0).astype(int) * 8 + (d.email_is_free == 1).astype(int) * 16
        + d.fraud_bool.astype(int) * 32)
data = {
    "emails": d.device_distinct_emails_8w.astype(int).tolist(),
    "crs": d.credit_risk_score.astype(int).tolist(),
    "limit": d.proposed_credit_limit.astype(int).tolist(),
    # floored to 4 decimals: exact for any "< t" test where t is a multiple of 0.0001
    "sim": [math.floor(v * 10000) for v in d.name_email_similarity],
    "bits": bits.tolist(),
    "month": d.month.astype(int).tolist(),
}
assert all(float(v) == int(v) for v in d.proposed_credit_limit)

# reproduce the workbook with the same packed values
f = {"F1": pd.Series(data["emails"]) >= rules["F1"]["thr"], "F2": pd.Series(data["crs"]) >= rules["F2"]["thr"],
     "F3": pd.Series(data["limit"]) >= rules["F3"]["thr"], "F4": (bits & 1) > 0, "F5": (bits & 2) > 0,
     "F6": pd.Series(data["sim"]) < round(rules["F6"]["thr"] * 10000), "F7": (bits & 4) > 0, "F8": (bits & 8) > 0, "F9": (bits & 16) > 0}
score = sum(f[k].astype(int) * rules[k]["pts"] for k in f)
tier = pd.cut(score, [-1, tiers["Medium"]["min"] - 1, tiers["High"]["min"] - 1, tiers["Critical"]["min"] - 1, 99],
              labels=["Low", "Medium", "High", "Critical"])
got = pd.DataFrame({"t": tier, "fr": d.fraud_bool}).groupby("t", observed=True).fr.agg(["size", "sum"])
expect = {"Critical": (1010, 78), "High": (2317, 64), "Medium": (7282, 109), "Low": (19391, 112)}
for t, v in expect.items():
    assert tuple(int(x) for x in got.loc[t]) == v, (t, tuple(got.loc[t]), v)
print("Packed data reproduces the workbook tiers:", expect)

payload = {"rules": rules, "tiers": tiers, "lastDev": last_dev, "d": data}
page = Path("docs/template.html").read_text().replace("__DATA__", json.dumps(payload, separators=(",", ":")))
Path("docs/index.html").write_text(page)
print("wrote docs/index.html", round(len(page) / 1024), "KB")
