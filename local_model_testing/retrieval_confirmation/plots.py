"""Standalone thesis figures derived only from saved experiment data."""

import csv
import subprocess
import sys

from .common import RUN, read


def main():
    try:
        import matplotlib
    except ImportError:
        target = "/tmp/confirmation-plot-deps"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--target",
                target,
                "matplotlib==3.10.7",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        sys.path.insert(0, target)
        import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    data = read(RUN / "offline/benchmark-verification.json")
    destination = RUN / "figures"
    destination.mkdir(exist_ok=True)
    plt.rcParams.update(
        {
            "font.size": 10,
            "svg.fonttype": "none",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    def save(fig, name):
        fig.tight_layout()
        for ext in ("svg", "png"):
            fig.savefig(destination / (name + "." + ext), dpi=200, bbox_inches="tight")
        plt.close(fig)

    configs = ["medical_base", "medical_adapter"]
    labels = ["Base", "Adapter"]
    colors = ["#2563a6", "#bc5d24"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    keys = ["exact_total_score_agreement", "schema_valid_rate_all_planned"]
    for i, c in enumerate(configs):
        m = data["medical"][c]
        values = [m[k] for k in keys] + [m["contract_valid"] / m["planned"]]
        bars = axes[0].bar(
            np.arange(3) + (i - 0.5) * 0.35,
            values,
            0.35,
            label=labels[i],
            color=colors[i],
        )
        axes[0].bar_label(
            bars, labels=[f"{x:.1%}" for x in values], padding=3, fontsize=8
        )
    axes[0].set_xticks(
        range(3), ["Exact total\n(and vector)", "Schema valid", "Full contract valid"]
    )
    axes[0].set_ylim(0, 1.15)
    axes[0].legend(loc="lower right")
    axes[0].set_title("Fixed reference evidence: 200 samples/config")
    values = [data["medical"][c]["mae_normalized"] for c in configs]
    bars = axes[1].bar(labels, values, color=colors)
    axes[1].bar_label(
        bars,
        labels=[
            f"{v:.4f}; n={data['medical'][c]['mae_n']}" for c, v in zip(configs, values)
        ],
        padding=4,
    )
    axes[1].set_ylim(0, 0.17)
    axes[1].set_ylabel("MAE / maximum score")
    axes[1].set_title("Numeric errors only where contract valid")
    save(fig, "medical-fixed-evidence")

    paired = data["paired_outcomes"]
    outcome_keys = [
        "base_1_adapter_1",
        "base_0_adapter_1",
        "base_1_adapter_0",
        "base_0_adapter_0",
    ]
    fig, ax = plt.subplots(figsize=(7, 3))
    bars = ax.barh(
        [
            "Both correct",
            "Adapter only correct",
            "Base only correct",
            "Neither correct",
        ],
        [paired.get(k, 0) for k in outcome_keys],
        color=["#4c7d69", colors[1], colors[0], "#777777"],
    )
    ax.bar_label(bars, padding=3)
    ax.set_xlim(0, max(paired.values()) * 1.15)
    ax.set_xlabel("Paired samples, n=200")
    ax.invert_yaxis()
    save(fig, "medical-paired-outcomes")

    with (RUN / "offline/medical-by-group.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        grouped = list(csv.DictReader(stream))
    types = sorted({r["group"] for r in grouped if r["dimension"] == "answer_type"})
    fig, ax = plt.subplots(figsize=(9, 4))
    for i, c in enumerate(configs):
        group = {
            r["group"]: r
            for r in grouped
            if r["dimension"] == "answer_type" and r["config"] == c
        }
        invalid = [
            int(group[t]["failed_attempts"]) / int(group[t]["planned"]) for t in types
        ]
        wrong = [
            (
                int(group[t]["contract_valid"])
                - round(
                    float(group[t]["exact_total_score_agreement"])
                    * int(group[t]["planned"])
                )
            )
            / int(group[t]["planned"])
            for t in types
        ]
        x = np.arange(len(types)) + (i - 0.5) * 0.36
        ax.bar(
            x, wrong, 0.36, color=colors[i], label=labels[i] + ": valid grade mismatch"
        )
        ax.bar(
            x,
            invalid,
            0.36,
            bottom=wrong,
            color=colors[i],
            hatch="///",
            alpha=0.4,
            label=labels[i] + ": contract/runtime failure",
        )
    ax.set_xticks(range(len(types)), types)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Non-agreement / declared samples in group")
    ax.legend(fontsize=8)
    save(fig, "medical-errors-by-answer-type")

    fig, ax = plt.subplots(figsize=(7, 3.6))
    for i, mode in enumerate(("vector", "hybrid")):
        m = data["retrieval"][mode]
        bars = ax.bar(
            np.arange(2) + (i - 0.5) * 0.35,
            [m["hit_at_5"], m["criterion_evidence_coverage_proxy"]],
            0.35,
            color=colors[i],
            label=mode,
        )
        ax.bar_label(bars, fmt="%.2f", padding=3)
    ax.set_xticks([0, 1], ["Hit@5 proxy", "Complete source-span coverage proxy"])
    ax.set_ylim(0, 1.12)
    ax.legend()
    ax.set_title("Existing offline TF-IDF / graph snapshot: 50 questions")
    save(fig, "retrieval-offline-proxies")
    integration_path = RUN / "integration-metrics.json"
    if integration_path.exists() and read(integration_path)["cases"]:
        from matplotlib.colors import ListedColormap
        from matplotlib.patches import Patch

        current = read(integration_path)
        samples = list(dict.fromkeys(c["sample_id"] for c in current["cases"]))
        matrix = np.full((len(samples), 2), 3)
        notes = {}
        for c in current["cases"]:
            pos = (samples.index(c["sample_id"]), ["vector", "hybrid"].index(c["mode"]))
            matrix[pos] = (
                2 if c["api_vector"] is None else (0 if c["exact_vector"] else 1)
            )
            notes[pos] = (
                str(c["api_vector"]) if c["api_vector"] is not None else "N/A"
            ) + (" *" if c["attempt_status"] == "teaching_failed" else "")
        palette = ["#cde4d8", "#f5d6bf", "#e7b5b9", "#eeeeee"]
        fig, ax = plt.subplots(figsize=(10, 4.7))
        ax.imshow(matrix, cmap=ListedColormap(palette), vmin=0, vmax=3, aspect="auto")
        ax.set_xticks(
            [0, 1],
            [
                f"{mode}: {current['strategy_results'][mode]['exact_vectors']}/6 reference vectors"
                for mode in ("vector", "hybrid")
            ],
        )
        ax.set_yticks(range(len(samples)), samples, fontsize=8)
        for (i, j), note in notes.items():
            ax.text(j, i, note, ha="center", va="center")
        ax.set_title("Medical API only: 3 development questions, 6 synthetic inputs")
        ax.legend(
            handles=[
                Patch(facecolor=palette[0], label="Reference vector matches"),
                Patch(facecolor=palette[1], label="Grade mismatch"),
            ],
            loc="upper center",
            bbox_to_anchor=(0.5, -0.11),
            ncol=2,
            fontsize=8,
        )
        fig.text(
            0.5,
            0.01,
            "* Teaching mock guard failed; Medical evaluation remains valid. Not a clinical accuracy estimate.",
            ha="center",
            fontsize=8,
        )
        save(fig, "integration-medical-pairs")
    print(
        {
            "figure_count": len(list(destination.glob("*.svg"))),
            "formats": ["svg", "png"],
            "data": "offline/benchmark-verification.json and CSV",
            "model_calls": 0,
        }
    )


if __name__ == "__main__":
    main()
