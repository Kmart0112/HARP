"""Convert supported model/dataset pairs into aligned calibration samples."""
import numpy as np
import pandas as pd
from dataclasses import dataclass

from harp.core.calibration import calculate_calibration
from harp.core.inference.place_predictor import predict_proba_from_payload
from harp.core.training.dataset_builder import BinaryDataset, year_holdout_masks


@dataclass(frozen=True)
class CalibrationPredictions:
    samples: pd.DataFrame
    metadata: dict


def evaluate_calibration(model, dataset, *, split="test", target=None, probability="raw",
                         n_bins=10, strategy="quantile", batch_size=32, metadata=None, entry_metadata=None):
    predictions = predict_calibration_samples(model, dataset, split=split, target=target, probability=probability,
                                              batch_size=batch_size, metadata=metadata, entry_metadata=entry_metadata)
    return calculate_calibration(predictions.samples, n_bins=n_bins, strategy=strategy, metadata=predictions.metadata)


def predict_calibration_samples(model, dataset, *, split="test", target=None, probability="raw",
                                batch_size=32, metadata=None, entry_metadata=None):
    """Evaluate HARP artifact payload + tabular data, or NnPredictor + PreparedNnDataset.

    A tabular frame uses its explicit split column, otherwise the saved year split.
    Use split='all' explicitly for a frame already restricted to evaluation rows.
    """
    if split not in {"train", "validation", "test", "all"}:
        raise ValueError("unknown evaluation split")
    if probability not in {"raw", "platt"}:
        raise ValueError("probability must be raw or platt")
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be positive")
    details = dict(metadata or {})
    if isinstance(model, dict):
        inferred = {"place": "is_place", "place_platt": "is_place", "win": "is_win"}.get(model.get("model_type"))
        target = target or inferred
        if not target:
            raise ValueError("target is required when the model has no recognized model_type")
        if inferred and target in {"is_place", "is_win"} and target != inferred:
            raise ValueError("target differs from the model task")
        frame, labels = _tabular_split(model, dataset, split, target)
        if target in model["feature_names"]:
            raise ValueError("target must not be a model feature")
        if not len(frame):
            raise ValueError("evaluation split is empty")
        p = predict_proba_from_payload(model, frame)
        if probability == "platt":
            from harp.core.training.algorithms.calibration.platt_logodds import apply_platt_logodds
            p = apply_platt_logodds(p, payload=model, df_feat=frame)
        identity_columns = ("race_id", "kettonum", "horse_number", "held_date")
        identity = frame[[name for name in identity_columns if name in frame]].copy()
        if entry_metadata is not None:
            if (not frame.index.is_unique or not entry_metadata.index.is_unique
                    or not frame.index.isin(entry_metadata.index).all()):
                raise ValueError("entry metadata must match dataset row IDs uniquely")
            aligned = entry_metadata.reindex(frame.index)
            for name in identity_columns:
                if name in aligned:
                    if name in identity and not identity[name].equals(aligned[name]):
                        raise ValueError("entry metadata conflicts with dataset identity")
                    identity[name] = aligned[name]
        samples = identity.reset_index(drop=True)
        samples["y_true"] = labels.to_numpy()
        samples["probability"] = p
        details.update(backend="lightgbm", model_type=model.get("model_type"),
                       feature_names=model["feature_names"], split_info=model.get("split_info"))
    else:
        # Keep optional torch imports out of tabular evaluation.
        from harp.core.nn.dataset import PreparedNnDataset
        from harp.core.nn.prediction import NnPredictor
        from harp.core.nn.training import evaluate_nn
        if not isinstance(model, NnPredictor) or not isinstance(dataset, PreparedNnDataset):
            raise TypeError("expected HARP model payload/tabular dataset or NnPredictor/PreparedNnDataset")
        from harp.core.nn.tasks import nn_target
        inferred = nn_target(model.task)
        if probability != "raw" or target not in {None, inferred}:
            raise ValueError("NN evaluation requires raw probabilities matching the model task")
        if (dataset.preprocessing != model.preprocessing or dataset.config.history_length != model.history_length
                or dataset.config.task != model.task):
            raise ValueError("NN dataset preprocessing/history/task differs from the model contract")
        target = inferred
        if split == "all":
            selected = dataset.dataset.select_races(tuple(p.race_id for p in dataset.partitions if p.exclusion_reason is None))
            summaries = list(dataset.summary.values())
        else:
            selected = dataset.split(split)
            summaries = [dataset.summary[split]]
        samples = evaluate_nn(model.model, selected, batch_size=batch_size, device=model.device).calibration_samples
        samples = samples.merge(selected.entry_metadata, on=["race_id", "kettonum"],
                                how="left", validate="one_to_one")
        if samples[["horse_number", "held_date"]].isna().any().any():
            raise ValueError("NN prediction identity differs from dataset")
        details.update(backend="nn", device=model.device,
                       excluded_races=sum(s["excluded_races"] for s in summaries),
                       excluded_entries=sum(s["excluded_entries"] for s in summaries))
    details.update(split=split, target=target, probability=probability)
    return CalibrationPredictions(samples, details)


def _tabular_split(payload, dataset, split, target):
    if isinstance(dataset, BinaryDataset):
        if split == "all":
            raise ValueError("BinaryDataset requires train, validation or test")
        suffix = {"train": "tr", "validation": "val", "test": "test"}[split]
        frame, labels = getattr(dataset, "X_" + suffix), getattr(dataset, "y_" + suffix)
        if not frame.index.is_unique or not labels.index.is_unique or set(frame.index) != set(labels.index):
            raise ValueError("dataset feature/label row IDs must match uniquely")
        return frame, labels.reindex(frame.index)
    if not isinstance(dataset, pd.DataFrame) or target not in dataset:
        raise ValueError("tabular dataset must contain the target column")
    if not dataset.columns.is_unique:
        raise ValueError("dataset columns must be unique")
    if split == "all":
        frame = dataset
    elif "split" in dataset:
        if not dataset["split"].isin(["train", "validation", "test"]).all():
            raise ValueError("invalid or missing dataset split")
        if "race_id" in dataset and dataset.groupby("race_id")["split"].nunique().gt(1).any():
            raise ValueError("a race must not cross dataset splits")
        frame = dataset.loc[dataset["split"].eq(split)]
    else:
        info = payload.get("split_info", {})
        required = ("train_year_start", "train_year_end", "test_year")
        if not all(name in info for name in required):
            raise ValueError("dataset needs a split column or model year split; use split='all' for evaluation-only data")
        if "held_year" in dataset:
            years = pd.to_numeric(dataset.held_year, errors="raise")
        elif "held_date" in dataset:
            years = pd.to_datetime(dataset.held_date, errors="raise").dt.year
        else:
            raise ValueError("year split requires held_year or held_date")
        if years.isna().any() or not np.equal(years, np.floor(years)).all():
            raise ValueError("invalid dataset year")
        masks = year_holdout_masks(years, **{key: int(info[key]) for key in required})
        frame = dataset.loc[masks[split]]
    return frame, frame[target]
