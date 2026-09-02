from __future__ import annotations

from typing import Any, Mapping

import lightgbm as lgb

from .contracts import TrainResult
from .dataset_builder import BinaryDataset
from .metrics import calc_binary_metrics, make_feature_importance


def train_binary_lgbm(
    ds: BinaryDataset,
    *,
    model_params: Mapping[str, Any],
    fit_kwargs: Mapping[str, Any] | None = None,
) -> TrainResult:
    model = lgb.LGBMClassifier(**dict(model_params))
    model_fit_kwargs = dict(fit_kwargs or {})
    model_fit_kwargs.setdefault("categorical_feature", ds.cat_features)
    model.fit(ds.X_tr, ds.y_tr, **model_fit_kwargs)

    proba_test = model.predict_proba(ds.X_test)[:, 1].astype(float)
    metrics = calc_binary_metrics(ds.y_test, proba_test)
    fi = make_feature_importance(
        ds.X_tr.columns,
        model.booster_.feature_importance(importance_type="gain"),
        model.booster_.feature_importance(importance_type="split"),
    )
    return TrainResult(model=model, feature_importance=fi, metrics=metrics)
