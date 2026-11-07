"""Report charts for the KYC application risk profiling project.

Reads the rule thresholds, points and tier cut-offs from the workbook's Ref_Rules sheet,
re-scores BAF_Sample_30k.csv in Python, checks the result against the workbook's Tier_Summary,
and saves the charts to charts/. Run: python charts.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import openpyxl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from matplotlib.patches import Patch

WB = "KYC_Risk_Profiling_Solved.xlsx"
OUT = Path("charts"); OUT.mkdir(exist_ok=True)
BLUE, ORANGE, GREY, INK, INK2, BG = "#2a78d6", "#eb6834", "#9a9a95", "#0b0b0b", "#52514e", "#fcfcfb"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c9c8c3", "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK, "figure.facecolor": BG, "axes.facecolor": BG})
NOTE = "Source: Bank Account Fraud (BAF) Suite, NeurIPS 2022 (synthetic) · working sample of 30,000 applications"

def save(fig, name):
    fig.tight_layout(); fig.savefig(OUT / name, dpi=160, bbox_inches="tight"); plt.close(fig)

# ---------- rules from the workbook
ws = openpyxl.load_workbook(WB, data_only=True)["Ref_Rules"]
rules, tiers, last_dev = [], {}, None
for row in ws.iter_rows(values_only=True):
    if row[0] and str(row[0]).startswith("F") and len(str(row[0])) == 2:
        rules.append(dict(flag=row[0], name=row[1], col=row[2], op=row[3], thr=row[4], pts=row[5]))
    elif row[0] in ("Low", "Medium", "High", "Critical"):
        tiers[row[0]] = row[1]
    elif row[0] == "Last development month":
        last_dev = row[1]

order = ["Critical", "High", "Medium", "Low"]
d = pd.read_csv("BAF_Sample_30k.csv")
def flag(r):
    if r["flag"] == "F4":                       # both phone numbers invalid
        return (d.phone_home_valid == 0) & (d.phone_mobile_valid == 0)
    x = d[r["col"]]
    return {">=": x >= r["thr"], "<": x < r["thr"], "=": x == r["thr"]}[r["op"]]
F = pd.DataFrame({r["flag"]: flag(r) for r in rules})
d["score"] = sum(F[r["flag"]].astype(int) * r["pts"] for r in rules)
d["tier"] = np.select([d.score >= tiers["Critical"], d.score >= tiers["High"], d.score >= tiers["Medium"]],
                      ["Critical", "High", "Medium"], "Low")
base = round(d.fraud_bool.mean(), 4)

# ---------- check against the workbook before drawing anything
ts = openpyxl.load_workbook(WB, data_only=True)["Tier_Summary"]
wb_counts = {}
for r in ts.iter_rows(values_only=True):          # first block = all 30,000 applications
    if r[0] in order and r[0] not in wb_counts: wb_counts[r[0]] = (r[1], r[3])
py_counts = d.groupby("tier").fraud_bool.agg(["size", "sum"])
for t in order:
    assert tuple(int(v) for v in py_counts.loc[t]) == wb_counts[t], f"{t}: Python {tuple(py_counts.loc[t])} vs workbook {wb_counts[t]}"
print("Tier counts match the workbook:", {t: wb_counts[t] for t in order})

# ---------- 1. fraud rate by tier, development vs test months
d["period"] = np.where(d.month <= last_dev, "dev", "test")
rate = d.pivot_table(index="tier", columns="period", values="fraud_bool", aggfunc="mean").loc[order]
fig, ax = plt.subplots(figsize=(8, 3.8))
x = np.arange(len(order)); w = 0.36
for i, (col, colr, lab) in enumerate([("dev", BLUE, f"Development months (0–{last_dev})"),
                                      ("test", ORANGE, f"Unseen test months ({last_dev + 1}–{d.month.max()})")]):
    ax.bar(x + (i - 0.5) * w, rate[col], width=w - 0.04, color=colr, label=lab)
    for xi, v in zip(x, rate[col]):
        ax.text(xi + (i - 0.5) * w, v + 0.002, f"{v:.1%}", ha="center", fontsize=9, color=INK2, zorder=4,
                bbox=dict(facecolor=BG, edgecolor="none", pad=1))
ax.axhline(base, color=GREY, lw=1, ls="--", label=f"Overall fraud rate {base:.2%}")
ax.set_xticks(x, [f"{t} tier" for t in order]); ax.set_ylim(0, 0.115)
ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0)); ax.set_ylabel("Fraud rate")
ax.legend(frameon=False, loc="upper right")
ax.set_title("Fraud rate falls tier by tier, and the order holds on unseen months", loc="left", fontsize=11, color=INK)
fig.text(0.01, -0.03, NOTE, fontsize=8, color=INK2)
save(fig, "01_fraud_rate_by_tier.png")

# ---------- 2. share of applications vs share of fraud
share = pd.DataFrame({"apps": d.tier.value_counts(normalize=True),
                      "fraud": d[d.fraud_bool == 1].tier.value_counts(normalize=True)}).loc[order]
top2 = share.loc[["Critical", "High"]].sum()
fig, ax = plt.subplots(figsize=(8, 3.8))
for i, (col, colr, lab) in enumerate([("apps", GREY, "Share of applications"), ("fraud", BLUE, "Share of all fraud")]):
    ax.bar(x + (i - 0.5) * w, share[col], width=w - 0.04, color=colr, label=lab)
    for xi, v in zip(x, share[col]):
        ax.text(xi + (i - 0.5) * w, v + 0.01, f"{v:.1%}", ha="center", fontsize=9, color=INK2)
ax.set_xticks(x, [f"{t} tier" for t in order]); ax.set_ylim(0, 0.75)
ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0)); ax.legend(frameon=False, loc="upper left")
ax.set_title(f"High + Critical: {top2.apps:.1%} of applications but {top2.fraud:.1%} of all fraud",
             loc="left", fontsize=11, color=INK)
fig.text(0.01, -0.03, NOTE + f" · {int(d.fraud_bool.sum())} fraud cases", fontsize=8, color=INK2)
save(fig, "02_applications_vs_fraud.png")

# ---------- 3. lift of each red flag
lift = pd.DataFrame([{"flag": r["flag"], "name": r["name"], "pts": r["pts"],
                      "lift": d.fraud_bool[F[r["flag"]]].mean() / base, "n": int(F[r["flag"]].sum())} for r in rules])
lift = lift.sort_values("lift")
fig, ax = plt.subplots(figsize=(8.5, 4.6))
ax.barh([f"{f}  {n}" for f, n in zip(lift.flag, lift.name)], lift.lift, color=BLUE, height=0.62)
for i, (v, p, n) in enumerate(zip(lift.lift, lift.pts, lift.n)):
    ax.text(v + 0.05, i, f"{v:.1f}x  ·  {p} pt{'s' if p > 1 else ''}  ·  {n:,} flagged", va="center", fontsize=8.5, color=INK2)
ax.axvline(1, color=GREY, lw=1, ls="--")
ax.set_xlim(0, 5.6); ax.set_xlabel("Lift: fraud rate among flagged applications ÷ overall rate (dashed line 1.0x = no better than average)")
fig.suptitle("Each red flag tested against outcomes; stronger flags earn more points", x=0.01, ha="left", fontsize=11, color=INK)
fig.text(0.01, -0.02, NOTE, fontsize=8, color=INK2)
save(fig, "03_red_flag_lift.png")

# ---------- 4. fairness check by age group (age is NOT in the score)
d["age_group"] = pd.cut(d.customer_age, [0, 29, 49, 200], labels=["Under 30", "30–49", "50+"])
fa = d.groupby("age_group", observed=True).agg(n=("tier", "size"),
                                               high=("tier", lambda s: s.isin(["Critical", "High"]).mean()),
                                               fraud=("fraud_bool", "mean"))
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.bar(fa.index.astype(str), fa.high, color=BLUE, width=0.55)
for i, (h, f, n) in enumerate(zip(fa.high, fa.fraud, fa.n)):
    ax.text(i, h + 0.006, f"{h:.1%} sent to High/Critical\nfraud rate {f:.2%} · n = {n:,}", ha="center", fontsize=8.5, color=INK2)
ax.set_ylim(0, 0.27); ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
ax.set_ylabel("Share in High or Critical tier")
ratio = fa.high["50+"] / fa.high["Under 30"]
ax.set_title(f"Fairness check: 50+ applicants reach High/Critical {ratio:.1f}x as often as under-30s",
             loc="left", fontsize=11, color=INK)
fig.text(0.01, -0.04, NOTE + " · age is not used in the score; the gap follows the higher fraud rate in older groups and needs review before real use",
         fontsize=8, color=INK2, wrap=True)
save(fig, "04_fairness_by_age.png")
print("Charts saved to", OUT)
