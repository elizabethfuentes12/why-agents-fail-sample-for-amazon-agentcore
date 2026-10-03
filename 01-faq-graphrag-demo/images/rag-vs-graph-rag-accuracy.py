import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RED, GREEN = "#dc2626", "#16a34a"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spterminal":False} if False else {})

cats = ["Aggregation", "Count", "Filtering", "Multi-hop", "Missing Data"]
rag  = [0, 20, 40, 10, 30]
graph= [100, 100, 100, 100, 100]
x = np.arange(len(cats)); w = 0.38
fig, ax = plt.subplots(figsize=(10, 5), dpi=200)
ax.bar(x - w/2, rag,   w, label="RAG (FAISS)",      color=RED,   edgecolor="white")
ax.bar(x + w/2, graph, w, label="Graph-RAG (Neo4j)", color=GREEN, edgecolor="white")
ax.set_ylabel("Accuracy (%)", fontsize=12, fontweight="bold")
ax.set_title("RAG vs Graph-RAG — Accuracy by Query Type", fontsize=15, fontweight="bold", pad=14)
ax.set_xticks(x); ax.set_xticklabels(cats, fontsize=11)
ax.set_ylim(0, 110); ax.legend(frameon=False, fontsize=11, loc="lower right")
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", alpha=0.25)
for i,(r,g) in enumerate(zip(rag,graph)):
    ax.text(i-w/2, r+2, f"{r}%", ha="center", fontsize=9, color=RED, fontweight="bold")
    ax.text(i+w/2, g+2, f"{g}%", ha="center", fontsize=9, color=GREEN, fontweight="bold")
fig.tight_layout()
fig.savefig("accuracy_chart.png", bbox_inches="tight")
print("saved accuracy_chart.png")
