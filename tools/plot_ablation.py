import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid")

df_gain = pd.read_csv("experiments/ablation_results.csv")
df_drop = pd.read_csv("experiments/ablation_remove_one_results.csv")

fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# 1. Gain distribution by transition
sns.boxplot(ax=axes[0,0], data=df_gain, x="transition_name", y="gain")
axes[0,0].set_title("Single-operator gain per transition")
axes[0,0].set_xlabel("Transition")
axes[0,0].set_ylabel("Score gain vs greedy")

# 2. Mean gain by days
sns.lineplot(ax=axes[0,1], data=df_gain, x="days", y="gain", hue="transition_name", marker="o")
axes[0,1].set_title("Mean gain vs days")
axes[0,1].set_ylabel("Score gain")

# 3. Mean delta vs baseline (remove-one)
mean_drop = df_drop.groupby("removed_name")["delta_vs_baseline"].mean().reset_index()
sns.barplot(ax=axes[1,0], data=mean_drop, x="removed_name", y="delta_vs_baseline", color="tomato")
axes[1,0].set_title("Mean score drop when removing transition")
axes[1,0].set_ylabel("Final score change (removed - baseline)")

# 4. Delta heatmap by days
pivot = df_drop.groupby(["removed_name","days"])["delta_vs_baseline"].mean().unstack()
sns.heatmap(pivot, ax=axes[1,1], annot=True, fmt=".2f", cmap="coolwarm", center=0)
axes[1,1].set_title("Mean score drop by days")
axes[1,1].set_xlabel("Days")
axes[1,1].set_ylabel("Removed transition")

plt.tight_layout()
plt.savefig("experiments/ablation_plots.png", dpi=200)
plt.show()