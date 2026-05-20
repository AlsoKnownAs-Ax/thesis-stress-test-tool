from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


USER_ORDER = [50, 125, 250]
WORKLOAD_ORDER = ["easy", "medium", "hard"]
VARIANT_ORDER = ["unary", "stream", "stream_ndjson"]

SUM_COLUMNS = {
    "requests",
    "failures",
    "received_items_mismatch_count",
    "total_response_bytes",
    "docker_samples",
}

METRICS = [
    {
        "column": "median_response_time_ms",
        "title": "Hard Workload: Median Response Time by Variant and User Load",
        "ylabel": "Median response time (ms)",
        "output": "hard_median_response_time.png",
    },
    {
        "column": "p95_response_time_ms",
        "title": "Hard Workload: P95 Response Time by Variant and User Load",
        "ylabel": "P95 response time (ms)",
        "output": "hard_p95_response_time.png",
    },
    {
        "column": "time_to_first_byte_ms",
        "title": "Hard Workload: Time to First Byte by Variant and User Load",
        "ylabel": "Time to first byte (ms)",
        "output": "hard_time_to_first_byte.png",
    },
    {
        "column": "time_to_first_item_ms",
        "title": "Hard Workload: Time to First Item by Variant and User Load",
        "ylabel": "Time to first item (ms)",
        "output": "hard_time_to_first_item.png",
    },
    {
        "column": "throughput_rps",
        "title": "Hard Workload: Throughput by Variant and User Load",
        "ylabel": "Throughput (requests/sec)",
        "output": "hard_throughput.png",
    },
    {
        "column": "docker_mem_avg_mib",
        "title": "Hard Workload: Average Docker Memory Usage by Variant and User Load",
        "ylabel": "Average memory usage (MiB)",
        "output": "hard_memory_avg.png",
    },
    {
        "column": "docker_cpu_avg_percent",
        "title": "Hard Workload: Average Docker CPU Usage by Variant and User Load",
        "ylabel": "Average CPU usage (%)",
        "output": "hard_cpu_avg.png",
    },
    {
        "column": "error_rate",
        "title": "Hard Workload: Error Rate by Variant and User Load",
        "ylabel": "Error rate (%)",
        "output": "hard_error_rate.png",
        "skip_if_all_zero": True,
    },
    {
        "column": "avg_response_bytes",
        "title": "Hard Workload: Average Response Size by Variant and User Load",
        "ylabel": "Average response size (bytes)",
        "output": "hard_avg_response_size.png",
    },
]

LINE_METRICS = [
    {
        "column": "median_response_time_ms",
        "title": "Hard Workload: Median Response Time Trend by Variant",
        "ylabel": "Median response time (ms)",
        "output": "hard_median_response_time_trend.png",
    },
    {
        "column": "p95_response_time_ms",
        "title": "Hard Workload: P95 Response Time Trend by Variant",
        "ylabel": "P95 response time (ms)",
        "output": "hard_p95_response_time_trend.png",
    },
    {
        "column": "time_to_first_byte_ms",
        "title": "Hard Workload: Time to First Byte Trend by Variant",
        "ylabel": "Time to first byte (ms)",
        "output": "hard_time_to_first_byte_trend.png",
    },
    {
        "column": "time_to_first_item_ms",
        "title": "Hard Workload: Time to First Item Trend by Variant",
        "ylabel": "Time to first item (ms)",
        "output": "hard_time_to_first_item_trend.png",
    },
    {
        "column": "throughput_rps",
        "title": "Hard Workload: Throughput Trend by Variant",
        "ylabel": "Throughput (requests/sec)",
        "output": "hard_throughput_trend.png",
    },
    {
        "column": "docker_mem_avg_mib",
        "title": "Hard Workload: Average Docker Memory Usage Trend",
        "ylabel": "Average memory usage (MiB)",
        "output": "hard_memory_avg_trend.png",
    },
    {
        "column": "docker_cpu_avg_percent",
        "title": "Hard Workload: Average Docker CPU Usage Trend",
        "ylabel": "Average CPU usage (%)",
        "output": "hard_cpu_avg_trend.png",
    },
    {
        "column": "avg_response_bytes",
        "title": "Hard Workload: Average Response Size Trend by Variant",
        "ylabel": "Average response size (bytes)",
        "output": "hard_avg_response_size_trend.png",
    },
]

PAIRWISE_COMPARISONS = [
    ("unary", "stream", "unary_vs_stream"),
    ("stream", "stream_ndjson", "stream_vs_stream_ndjson"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot hard workload benchmark results from CSV files."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Folder containing CSV files or one or more CSV file paths.",
    )
    return parser.parse_args()


def collect_csv_files(paths: Iterable[str]) -> list[Path]:
    input_paths = [Path(p) for p in paths]
    if len(input_paths) == 1 and input_paths[0].is_dir():
        workload_dirs = [
            input_paths[0] / workload
            for workload in WORKLOAD_ORDER
            if (input_paths[0] / workload).is_dir()
        ]
        if workload_dirs:
            files = []
            for workload_dir in workload_dirs:
                files.extend(sorted(workload_dir.glob("*.csv")))
            return files
        return sorted(input_paths[0].glob("*.csv"))
    files = []
    for path in input_paths:
        if path.is_dir():
            workload_dirs = [
                path / workload
                for workload in WORKLOAD_ORDER
                if (path / workload).is_dir()
            ]
            if workload_dirs:
                for workload_dir in workload_dirs:
                    files.extend(sorted(workload_dir.glob("*.csv")))
            else:
                files.extend(sorted(path.glob("*.csv")))
        else:
            files.append(path)
    return files


def load_csvs(files: Iterable[Path]) -> pd.DataFrame:
    frames = []
    for file_path in files:
        if not file_path.exists():
            print(f"Warning: CSV file not found: {file_path}")
            continue
        frames.append(pd.read_csv(file_path))
    if not frames:
        raise SystemExit("No CSV files found to process.")
    return pd.concat(frames, ignore_index=True)


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "workload" in df.columns:
        df["workload"] = df["workload"].astype(str).str.strip().str.lower()
        unexpected = sorted(set(df["workload"].dropna()) - set(WORKLOAD_ORDER))
        if unexpected:
            print(
                "Warning: Unexpected workloads found and ignored: "
                + ", ".join(unexpected)
            )
            df = df[df["workload"].isin(WORKLOAD_ORDER)]

    if "variant" in df.columns:
        df["variant"] = df["variant"].astype(str).str.strip()
        variant_map = {
            "stream": "stream",
            "streaming": "stream",
            "streaming_aggregated": "stream",
            "stream_ndjson": "stream_ndjson",
            "streaming_ndjson": "stream_ndjson",
        }
        df["variant"] = df["variant"].replace(variant_map)
        unexpected = sorted(set(df["variant"].dropna()) - set(VARIANT_ORDER))
        if unexpected:
            print(
                "Warning: Unexpected variants found and ignored: "
                + ", ".join(unexpected)
            )
            df = df[df["variant"].isin(VARIANT_ORDER)]

    numeric_columns = [col for col in df.columns if col not in {"timestamp", "workload", "variant", "endpoint", "method"}]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "users" in df.columns:
        df["users"] = pd.to_numeric(df["users"], errors="coerce")

    grouped = aggregate_duplicates(df)
    grouped["workload"] = pd.Categorical(
        grouped["workload"], categories=WORKLOAD_ORDER, ordered=True
    )
    grouped["users"] = pd.Categorical(grouped["users"], categories=USER_ORDER, ordered=True)
    grouped["variant"] = pd.Categorical(grouped["variant"], categories=VARIANT_ORDER, ordered=True)
    grouped = grouped.sort_values(["workload", "users", "variant"])\
        .reset_index(drop=True)
    return grouped


def aggregate_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = ["workload", "users", "variant", "endpoint", "method"]
    existing_group_cols = [col for col in group_cols if col in df.columns]

    numeric_cols = [
        col for col in df.select_dtypes(include=["number"]).columns
        if col not in existing_group_cols
    ]
    agg_map = {}
    for col in numeric_cols:
        if col in SUM_COLUMNS:
            agg_map[col] = "sum"
        else:
            agg_map[col] = "mean"

    non_numeric_cols = [
        col for col in df.columns
        if col not in numeric_cols and col not in existing_group_cols
    ]
    for col in non_numeric_cols:
        agg_map[col] = "first"

    if existing_group_cols:
        return df.groupby(existing_group_cols, dropna=False).agg(agg_map).reset_index()
    return df


def ensure_graphs_dir(root: Path) -> Path:
    graphs_dir = root / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)
    return graphs_dir


def plot_grouped_bar(
    df: pd.DataFrame,
    metric: dict,
    graphs_dir: Path,
    variants: list[str],
    suffix: str,
    workload: str,
) -> None:
    column = metric["column"]
    if column not in df.columns:
        print(f"Warning: Missing column '{column}'. Skipping graph.")
        return

    series = df[column]
    if series.isna().all():
        print(f"Warning: Column '{column}' has no data. Skipping graph.")
        return

    pivot = df.pivot_table(index="users", columns="variant", values=column, aggfunc="mean")
    pivot = pivot.reindex(index=USER_ORDER, columns=VARIANT_ORDER)

    variants_to_plot = [v for v in variants if v in pivot.columns and not pivot[v].isna().all()]
    if not variants_to_plot:
        print(f"Warning: No data to plot for '{column}'. Skipping graph.")
        return

    x = np.arange(len(pivot.index))
    bar_width = 0.8 / len(variants_to_plot)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for idx, variant in enumerate(variants_to_plot):
        offset = (idx - (len(variants_to_plot) - 1) / 2) * bar_width
        values = pivot[variant].values
        ax.bar(x + offset, values, width=bar_width, label=variant)

    ax.set_title(build_workload_title(metric["title"], workload), fontsize=12)
    ax.set_xlabel("User load", fontsize=11)
    ax.set_ylabel(metric["ylabel"], fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([str(u) for u in pivot.index], fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    fig.tight_layout()

    output_path = graphs_dir / with_suffix(metric["output"], suffix)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_line_trend(
    df: pd.DataFrame,
    metric: dict,
    graphs_dir: Path,
    variants: list[str],
    suffix: str,
    workload: str,
) -> None:
    column = metric["column"]
    if column not in df.columns:
        print(f"Warning: Missing column '{column}'. Skipping line plot.")
        return

    series = df[column]
    if series.isna().all():
        print(f"Warning: Column '{column}' has no data. Skipping line plot.")
        return

    pivot = df.pivot_table(index="users", columns="variant", values=column, aggfunc="mean")
    pivot = pivot.reindex(index=USER_ORDER, columns=VARIANT_ORDER)

    variants_to_plot = [v for v in variants if v in pivot.columns and not pivot[v].isna().all()]
    if not variants_to_plot:
        print(f"Warning: No data to plot for '{column}'. Skipping line plot.")
        return

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for variant in variants_to_plot:
        ax.plot(
            pivot.index,
            pivot[variant].values,
            marker="o",
            linewidth=2,
            label=variant,
        )

    ax.set_title(build_workload_title(metric["title"], workload), fontsize=12)
    ax.set_xlabel("User load", fontsize=11)
    ax.set_ylabel(metric["ylabel"], fontsize=11)
    ax.set_xticks(USER_ORDER)
    ax.legend(fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    fig.tight_layout()

    output_path = graphs_dir / with_suffix(metric["output"], suffix)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def plot_workload_comparison_bar(
    df: pd.DataFrame,
    metric: dict,
    graphs_dir: Path,
    variants: list[str],
    suffix: str,
) -> None:
    column = metric["column"]
    if column not in df.columns:
        print(f"Warning: Missing column '{column}'. Skipping workload comparison.")
        return

    series = df[column]
    if series.isna().all():
        print(f"Warning: Column '{column}' has no data. Skipping workload comparison.")
        return

    pivot = df.pivot_table(index="workload", columns="variant", values=column, aggfunc="mean")
    pivot = pivot.reindex(index=WORKLOAD_ORDER, columns=VARIANT_ORDER)

    variants_to_plot = [v for v in variants if v in pivot.columns and not pivot[v].isna().all()]
    if not variants_to_plot:
        print(f"Warning: No data to plot for '{column}'. Skipping workload comparison.")
        return

    x = np.arange(len(pivot.index))
    bar_width = 0.8 / len(variants_to_plot)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for idx, variant in enumerate(variants_to_plot):
        offset = (idx - (len(variants_to_plot) - 1) / 2) * bar_width
        values = pivot[variant].values
        ax.bar(x + offset, values, width=bar_width, label=variant)

    ax.set_title(build_workload_comparison_title(metric["title"]), fontsize=12)
    ax.set_xlabel("Workload", fontsize=11)
    ax.set_ylabel(metric["ylabel"], fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([str(w) for w in pivot.index], fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    fig.tight_layout()

    output_path = graphs_dir / with_suffix(add_workload_tag(metric["output"]), suffix)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def summarize_results(df: pd.DataFrame) -> None:
    print("\nSummary by workload and user load:")
    for workload in WORKLOAD_ORDER:
        workload_df = df[df["workload"] == workload]
        if workload_df.empty:
            print(f"- {workload}: no data")
            continue
        for user in USER_ORDER:
            subset = workload_df[workload_df["users"] == user]
            if subset.empty:
                print(f"- {workload}, {user} users: no data")
                continue

            unary_vs_stream_median = compare_variants(
                subset, "median_response_time_ms", "unary", "stream", "min"
            )
            stream_vs_ndjson_median = compare_variants(
                subset, "median_response_time_ms", "stream", "stream_ndjson", "min"
            )
            unary_vs_stream_p95 = compare_variants(
                subset, "p95_response_time_ms", "unary", "stream", "min"
            )
            stream_vs_ndjson_p95 = compare_variants(
                subset, "p95_response_time_ms", "stream", "stream_ndjson", "min"
            )
            unary_vs_stream_ttf_item = compare_variants(
                subset, "time_to_first_item_ms", "unary", "stream", "min"
            )
            stream_vs_ndjson_ttf_item = compare_variants(
                subset, "time_to_first_item_ms", "stream", "stream_ndjson", "min"
            )
            unary_vs_stream_throughput = compare_variants(
                subset, "throughput_rps", "unary", "stream", "max"
            )
            stream_vs_ndjson_throughput = compare_variants(
                subset, "throughput_rps", "stream", "stream_ndjson", "max"
            )

            failures = subset.get("failures")
            error_rate = subset.get("error_rate")
            has_failures = failures is not None and (failures.fillna(0) > 0).any()
            has_error = error_rate is not None and (error_rate.fillna(0) > 0).any()

            expected = subset.get("expected_items_per_request")
            received = subset.get("received_items_avg")
            if expected is None or received is None:
                items_match = "n/a"
            else:
                comparison = (expected == received) | (expected.isna() | received.isna())
                items_match = "Yes" if comparison.all() else "No"

            mismatch_count = subset.get("received_items_mismatch_count")
            if mismatch_count is None:
                mismatch_zero = "n/a"
            else:
                mismatch_zero = "Yes" if (mismatch_count.fillna(0) == 0).all() else "No"

            median_values = format_variant_values(subset, "median_response_time_ms")
            median_note = f", median values={median_values}" if median_values else ""

            print(
                f"- {workload}, {user} users: "
                f"median unary vs stream={unary_vs_stream_median}, "
                f"median stream vs stream_ndjson={stream_vs_ndjson_median}, "
                f"p95 unary vs stream={unary_vs_stream_p95}, "
                f"p95 stream vs stream_ndjson={stream_vs_ndjson_p95}, "
                f"time to first item unary vs stream={unary_vs_stream_ttf_item}, "
                f"time to first item stream vs stream_ndjson={stream_vs_ndjson_ttf_item}, "
                f"throughput unary vs stream={unary_vs_stream_throughput}, "
                f"throughput stream vs stream_ndjson={stream_vs_ndjson_throughput}{median_note}, "
                f"failures or errors={'Yes' if (has_failures or has_error) else 'No'}, "
                f"received_items_avg matches expected={items_match}, "
                f"received_items_mismatch_count is 0={mismatch_zero}"
            )


def best_variant(df: pd.DataFrame, column: str, mode: str) -> str:
    if column not in df.columns:
        return "n/a"
    series = df[["variant", column]].dropna()
    if series.empty:
        return "n/a"
    if mode == "min":
        row = series.loc[series[column].idxmin()]
    else:
        row = series.loc[series[column].idxmax()]
    return str(row["variant"])


def compare_variants(
    df: pd.DataFrame,
    column: str,
    left_variant: str,
    right_variant: str,
    mode: str,
) -> str:
    if column not in df.columns or "variant" not in df.columns:
        return "n/a"

    left_values = df.loc[df["variant"] == left_variant, column].dropna()
    right_values = df.loc[df["variant"] == right_variant, column].dropna()

    if left_values.empty or right_values.empty:
        return "n/a"

    left_value = left_values.mean()
    right_value = right_values.mean()

    if np.isclose(left_value, right_value, equal_nan=True):
        return "tie"

    if mode == "min":
        return left_variant if left_value < right_value else right_variant
    return left_variant if left_value > right_value else right_variant


def format_variant_values(df: pd.DataFrame, column: str) -> str:
    if column not in df.columns or "variant" not in df.columns:
        return ""
    values = []
    for variant in VARIANT_ORDER:
        subset = df[df["variant"] == variant]
        if subset.empty:
            continue
        value = subset[column].dropna()
        if value.empty:
            continue
        values.append(f"{variant}={value.mean():.2f}")
    return "; ".join(values)


def with_suffix(filename: str, suffix: str) -> str:
    path = Path(filename)
    return f"{path.stem}_{suffix}{path.suffix}"


def add_workload_tag(filename: str) -> str:
    path = Path(filename)
    return f"{path.stem}_by_workload{path.suffix}"


def build_workload_title(title: str, workload: str) -> str:
    base = title.split(":", 1)[1].strip() if ":" in title else title
    return f"{workload.title()} Workload: {base}"


def build_workload_comparison_title(title: str) -> str:
    base = title.split(":", 1)[1].strip() if ":" in title else title
    base = base.replace("by Variant and User Load", "by Variant and Workload")
    return f"Workload Comparison: {base}"


def is_all_zero(df: pd.DataFrame, column: str) -> bool:
    if column not in df.columns:
        return False
    series = df[column].dropna()
    return not series.empty and (series == 0).all()


def main() -> None:
    args = parse_args()
    csv_files = collect_csv_files(args.paths)
    if not csv_files:
        raise SystemExit("No CSV files found to process.")

    df = load_csvs(csv_files)
    cleaned = clean_dataframe(df)

    output_csv = Path("hard_workload_summary.csv")
    cleaned.to_csv(output_csv, index=False)

    graphs_dir = ensure_graphs_dir(Path.cwd())
    for workload in WORKLOAD_ORDER:
        workload_df = cleaned[cleaned["workload"] == workload]
        if workload_df.empty:
            continue
        for metric in METRICS:
            if metric.get("skip_if_all_zero") and is_all_zero(workload_df, metric["column"]):
                print(f"All {workload} workload runs completed with 0% error rate.")
                continue
            for left, right, suffix in PAIRWISE_COMPARISONS:
                plot_grouped_bar(workload_df, metric, graphs_dir, [left, right], suffix, workload)
        for metric in LINE_METRICS:
            for left, right, suffix in PAIRWISE_COMPARISONS:
                plot_line_trend(workload_df, metric, graphs_dir, [left, right], suffix, workload)

    for metric in METRICS:
        if metric.get("skip_if_all_zero") and is_all_zero(cleaned, metric["column"]):
            print("All workload runs completed with 0% error rate.")
            continue
        for left, right, suffix in PAIRWISE_COMPARISONS:
            plot_workload_comparison_bar(cleaned, metric, graphs_dir, [left, right], suffix)

    summarize_results(cleaned)


if __name__ == "__main__":
    main()
