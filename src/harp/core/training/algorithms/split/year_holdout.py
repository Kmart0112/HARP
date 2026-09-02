from __future__ import annotations

import pandas as pd

from ...dataset_builder import BinaryDataset, build_binary_dataset


def build_year_holdout_dataset(
    df_train: pd.DataFrame,
    *,
    train_year_start: int,
    train_year_end: int,
    test_year: int,
    feature_names: list[str],
    cat_features: list[str],
    target_col: str,
) -> BinaryDataset:
    return build_binary_dataset(
        df=df_train,
        feature_names=feature_names,
        cat_features=cat_features,
        target_col=target_col,
        train_year_start=int(train_year_start),
        train_year_end=int(train_year_end),
        test_year=int(test_year),
    )
