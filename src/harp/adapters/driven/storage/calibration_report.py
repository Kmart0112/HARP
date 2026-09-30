"""Headless rendering and atomic publication of calibration artifacts."""
import json
from pathlib import Path
import tempfile
from hashlib import sha256
import math

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from harp.core.calibration import CalibrationReport


class FileCalibrationReport:
    def save(self, report: CalibrationReport, output_dir: str) -> dict[str, str]:
        destination = Path(output_dir).resolve()
        if destination.exists():
            raise FileExistsError(f"report output already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        names = {"plot": "calibration.png", "bins": "bins.csv", "metrics": "metrics.json"}
        with tempfile.TemporaryDirectory(prefix=".calibration-", dir=destination.parent) as temporary:
            staging = Path(temporary) / "report"
            staging.mkdir()
            report.bins.to_csv(staging / names["bins"], index=False)
            if report.predictions is not None:
                names["predictions"] = "predictions.parquet"
                report.predictions.to_parquet(staging / names["predictions"], index=False)
            document = {"metrics": report.metrics, "metadata": report.metadata}
            if report.odds_bands is not None:
                bands = report.odds_bands
                names.update(odds_metrics="odds_band_metrics.csv", odds_bins="odds_band_bins.csv",
                             odds_plot="odds_band_calibration.png")
                bands.metrics.to_csv(staging / names["odds_metrics"], index=False)
                bands.bins.to_csv(staging / names["odds_bins"], index=False)
                document["odds_bands"] = {"coverage": bands.coverage, "metadata": bands.metadata}
                _draw_odds_bands(report, staging / names["odds_plot"])
            (staging / names["metrics"]).write_text(json.dumps(
                document, ensure_ascii=False,
                indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
            figure = Figure(figsize=(7, 9), layout="constrained")
            FigureCanvasAgg(figure)
            curve, counts, histogram = figure.subplots(3, 1, gridspec_kw={"height_ratios": [4, 1, 1.2]})
            curve.plot([0, 1], [0, 1], "--", color="0.5", label="Perfect calibration")
            bins = report.bins
            curve.plot(bins.mean_probability, bins.observed_rate, "o-", label="Model")
            curve.set(xlim=(-.02, 1.02), ylim=(-.02, 1.02), xlabel="Mean predicted probability",
                      ylabel="Observed positive rate", title="Calibration curve")
            curve.grid(alpha=.25)
            curve.legend(loc="lower right")
            positions = range(1, len(bins) + 1)
            bars = counts.bar(positions, bins["count"])
            if len(bins) <= 20:
                counts.set_xticks(list(positions), [str(value + 1) for value in bins.bin])
                counts.bar_label(bars, fontsize=8, padding=2)
            counts.set(xlabel="Calibration bin (increasing probability)", ylabel="Count")
            counts.set_ylim(0, max(bins["count"]) * 1.3)
            hist = report.histogram
            histogram.bar(hist.lower, hist["count"], width=hist.upper - hist.lower, align="edge", edgecolor="white")
            histogram.set(xlim=(0, 1), xlabel="Predicted probability", ylabel="Count")
            details = report.metadata
            figure.suptitle(f"{details.get('target', 'binary')} | {details.get('split', '')} | "
                            f"{details.get('probability', 'raw')} | {details['strategy']}\n"
                            f"n={report.metrics['samples']:,}   Brier={report.metrics['brier']:.4f}   "
                            f"Logloss={report.metrics['logloss']:.4f}", fontsize=11)
            figure.savefig(staging / names["plot"], dpi=160)
            manifest = {"version": 1, "kind": "calibration_report",
                        "files": {name: sha256((staging / name).read_bytes()).hexdigest() for name in names.values()}}
            names["manifest"] = "manifest.json"
            (staging / names["manifest"]).write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
            staging.rename(destination)
        return {key: str(destination / name) for key, name in names.items()}


def _draw_odds_bands(report, path):
    bands = report.odds_bands
    count = len(bands.metrics)
    columns = min(4, count)
    rows = math.ceil(count / columns)
    figure = Figure(figsize=(3.3 * columns, 3.1 * rows), layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots(rows, columns, squeeze=False).ravel()
    for axis, row in zip(axes, bands.metrics.itertuples()):
        axis.plot([0, 1], [0, 1], "--", color=".6", linewidth=1)
        points = bands.bins.loc[bands.bins.band.eq(row.band)]
        if not points.empty:
            axis.plot(points.mean_probability, points.observed_rate, "o-", markersize=4)
        else:
            axis.text(.5, .5, "No available samples", ha="center", va="center", fontsize=9)
        status = " | small sample" if row.status == "small_sample" else ""
        axis.set(title=f"{row.odds_band} | n={row.samples:,}{status}", xlim=(0, 1), ylim=(0, 1),
                 xlabel="Mean predicted probability", ylabel="Observed rate")
        axis.grid(alpha=.2)
    for axis in axes[count:]:
        axis.set_visible(False)
    coverage, meta = bands.coverage, bands.metadata
    figure.suptitle(f"{report.metadata.get('split', '')} | {meta['market']} {meta.get('place_method') or ''} odds | "
                    f"{report.metadata.get('probability', 'raw')}\n"
                    f"Available {coverage['available_samples']:,}/{coverage['labelled_samples']:,} "
                    f"({coverage['available_fraction']:.1%}) | {meta['policy']['mode']}")
    figure.savefig(path, dpi=160)
