import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RED, GREEN = "#dc2626", "#16a34a"

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5), dpi=200)

# --- Panel 1: Accuracy ---
cats1 = ["Correct\nSelection", "Error\nRate"]
trad1 = [75, 25]
sem1  = [100, 0]
x = np.arange(len(cats1)); w = 0.38
ax1.bar(x - w/2, trad1, w, label="Traditional (29 tools)", color=RED,   edgecolor="white")
ax1.bar(x + w/2, sem1,  w, label="Semantic (3 tools)",     color=GREEN, edgecolor="white")
ax1.set_ylabel("Percentage (%)", fontsize=12, fontweight="bold")
ax1.set_title("Accuracy Comparison", fontsize=14, fontweight="bold", pad=12)
ax1.set_xticks(x); ax1.set_xticklabels(cats1, fontsize=11)
ax1.set_ylim(0, 115); ax1.legend(frameon=False, fontsize=10, loc="upper right")
ax1.spines[["top", "right"]].set_visible(False); ax1.grid(axis="y", alpha=0.25)
for i,(t,s) in enumerate(zip(trad1, sem1)):
    ax1.text(i-w/2, t+2, f"{t}%", ha="center", fontsize=10, color=RED,   fontweight="bold")
    ax1.text(i+w/2, s+2, f"{s}%", ha="center", fontsize=10, color=GREEN, fontweight="bold")

# --- Panel 2: Cost & performance (relative %) ---
cats2 = ["Tokens\nper Call", "Response\nTime"]
trad2 = [100, 100]   # baseline 100%
sem2  = [11, 38]     # 500/4500≈11%, response 38%
labels_trad = ["4,500", "100%"]
labels_sem  = ["500", "38%"]
ax2.bar(x - w/2, trad2, w, label="Traditional (29 tools)", color=RED,   edgecolor="white")
ax2.bar(x + w/2, sem2,  w, label="Semantic (3 tools)",     color=GREEN, edgecolor="white")
ax2.set_ylabel("Relative Cost (%)", fontsize=12, fontweight="bold")
ax2.set_title("Cost & Performance Comparison", fontsize=14, fontweight="bold", pad=12)
ax2.set_xticks(x); ax2.set_xticklabels(cats2, fontsize=11)
ax2.set_ylim(0, 115); ax2.legend(frameon=False, fontsize=10, loc="center right")
ax2.spines[["top", "right"]].set_visible(False); ax2.grid(axis="y", alpha=0.25)
for i,(t,lt) in enumerate(zip(trad2, labels_trad)):
    ax2.text(i-w/2, t+2, lt, ha="center", fontsize=10, color=RED, fontweight="bold")
for i,(s,ls) in enumerate(zip(sem2, labels_sem)):
    ax2.text(i+w/2, s+2, ls, ha="center", fontsize=10, color=GREEN, fontweight="bold")

fig.tight_layout()
fig.savefig("results_chart.png", bbox_inches="tight")
print("saved results_chart.png")
