import marimo

__generated_with = "0.22.4"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: notebook 全体で使うライブラリを読み込む。
    import os
    import random
    import re
    import shlex
    import sys
    from pathlib import Path

    import lightgbm as lgb
    import marimo as mo
    import numpy as np
    import pandas as pd
    from pydantic import BaseModel, Field

    return BaseModel, Field, Path, lgb, mo, np, os, pd, random, re, shlex, sys


@app.cell(hide_code=True)
def _(mo):
    # セル概要: notebook の目的を表示する。
    mo.md("""
    # LGBM 馬連向け Top2 Metrics

    - 粒度は馬ごと
    - 教師は `result_order <= 2`
    - 特徴量は複勝と同じ `place_v1`
    - `j_odds_tansho` を使って Platt calibration
    - レース内制約は各レースの確率和を `2` に寄せる
    - `platt_shift_top2` から max-entropy の unordered pair model で馬連確率も復元する
    """)
    return


@app.cell
def _(Path, sys):
    # セル概要: project root と notebook 用 helper を解決する。
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    SRC_ROOT = PROJECT_ROOT / "src"

    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from harp.controllers import (
        NotebookFeatureConfigController,
        build_notebook_config,
    )
    from pipeline.runtime_settings import load_pipeline_runtime_config
    from harp.shared.paths import notebook_analysis_cache_dir
    from harp.shared.db import read_sql_df

    runtime_config = load_pipeline_runtime_config()
    notebook_feature_config = NotebookFeatureConfigController(runtime_config)
    return (
        build_notebook_config,
        notebook_feature_config,
        notebook_analysis_cache_dir,
        read_sql_df,
        runtime_config,
    )


@app.cell
def _(mo):
    # セル概要: script mode と interactive mode を判定する。
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 設定セクション見出しを表示する。
    mo.md("""
    ## 1. 実行設定
    """)
    return


@app.cell
def _(BaseModel, Field, notebook_feature_config, runtime_config):
    # セル概要: notebook 実行設定の schema を定義する。
    class RunConfig(BaseModel):
        train_year_start: int = Field(default=2013)
        train_year_end: int = Field(default=2024)
        test_year: int = Field(default=2025)
        global_seed: int = Field(default=42)
        feature_set_name: str = Field(default="place_v1")
        registry_path: str = Field(default=notebook_feature_config.default_registry_path())
        main_parquet_path: str = Field(default="")
        db_url: str = Field(default=runtime_config.database.db_url)
        umaren_odds_table: str = Field(default="core.fct_race_umaren_odds_result")
        min_expected_return: float = Field(default=1.0)
        max_top_n: int = Field(default=10)

    cfg = RunConfig()
    return (cfg,)


@app.cell
def _(cfg, mo):
    # セル概要: interactive 実行時の入力 widget を表示する。
    feature_set_name_widget = mo.ui.text(
        label="Feature set name",
        value=cfg.feature_set_name,
        full_width=True,
    )
    registry_path_widget = mo.ui.text(
        label="Registry path",
        value=cfg.registry_path,
        full_width=True,
    )
    main_parquet_path_widget = mo.ui.text(
        label="Main parquet path",
        value=cfg.main_parquet_path,
        placeholder="notebook/tmp/analysis_cache/....parquet",
        full_width=True,
    )
    db_url_widget = mo.ui.text(
        label="DB URL",
        value=cfg.db_url,
        full_width=True,
    )
    umaren_odds_table_widget = mo.ui.text(
        label="Umaren odds table",
        value=cfg.umaren_odds_table,
        full_width=True,
    )
    min_expected_return_widget = mo.ui.number(
        label="Min expected return",
        value=float(cfg.min_expected_return),
        start=0.0,
        step=0.01,
        full_width=True,
    )
    max_top_n_widget = mo.ui.number(
        label="Max top-N sweep",
        value=int(cfg.max_top_n),
        start=1,
        step=1,
        full_width=True,
    )

    mo.vstack(
        [
            feature_set_name_widget,
            registry_path_widget,
            main_parquet_path_widget,
            db_url_widget,
            umaren_odds_table_widget,
            min_expected_return_widget,
            max_top_n_widget,
        ]
    )
    return (
        db_url_widget,
        feature_set_name_widget,
        main_parquet_path_widget,
        max_top_n_widget,
        min_expected_return_widget,
        registry_path_widget,
        umaren_odds_table_widget,
    )


@app.cell
def _(
    build_notebook_config,
    cfg,
    db_url_widget,
    feature_set_name_widget,
    is_script_mode,
    main_parquet_path_widget,
    max_top_n_widget,
    min_expected_return_widget,
    mo,
    notebook_analysis_cache_dir,
    registry_path_widget,
    umaren_odds_table_widget,
):
    # セル概要: UI / CLI を統合して実行時設定を確定する。
    if is_script_mode:
        resolved_cfg = build_notebook_config(
            type(cfg),
            defaults=cfg,
            cli_args=mo.cli_args(),
        )
    else:
        resolved_cfg = build_notebook_config(
            type(cfg),
            defaults=cfg,
            overrides={
                "db_url": str(db_url_widget.value).strip(),
                "feature_set_name": str(feature_set_name_widget.value).strip(),
                "main_parquet_path": str(main_parquet_path_widget.value).strip(),
                "max_top_n": int(max_top_n_widget.value),
                "min_expected_return": float(min_expected_return_widget.value),
                "registry_path": str(registry_path_widget.value).strip(),
                "umaren_odds_table": str(umaren_odds_table_widget.value).strip(),
            },
        )

    cache_dir = notebook_analysis_cache_dir()
    default_main = cache_dir / (
        f"m_train_race_horse_past5_{int(resolved_cfg.train_year_start)}_{int(resolved_cfg.test_year)}.parquet"
    )
    resolved_cfg = resolved_cfg.model_copy(
        update={
            "db_url": str(resolved_cfg.db_url).strip(),
            "feature_set_name": str(resolved_cfg.feature_set_name).strip(),
            "max_top_n": int(resolved_cfg.max_top_n),
            "main_parquet_path": str(resolved_cfg.main_parquet_path).strip() or str(default_main),
            "min_expected_return": float(resolved_cfg.min_expected_return),
            "registry_path": str(resolved_cfg.registry_path).strip(),
            "umaren_odds_table": str(resolved_cfg.umaren_odds_table).strip(),
        }
    )

    if not resolved_cfg.feature_set_name:
        raise ValueError("feature_set_name is required.")
    if not resolved_cfg.db_url:
        raise ValueError("db_url is required.")
    if not resolved_cfg.main_parquet_path:
        raise ValueError("main_parquet_path is required.")
    if not resolved_cfg.umaren_odds_table:
        raise ValueError("umaren_odds_table is required.")
    if int(resolved_cfg.max_top_n) < 1:
        raise ValueError("max_top_n must be >= 1.")
    return (resolved_cfg,)


@app.cell
def _(np, os, random, resolved_cfg):
    # セル概要: 乱数 seed を固定する。
    os.environ["PYTHONHASHSEED"] = str(int(resolved_cfg.global_seed))
    random.seed(int(resolved_cfg.global_seed))
    np.random.seed(int(resolved_cfg.global_seed))
    return


@app.cell(hide_code=True)
def _(mo, resolved_cfg):
    # セル概要: 確定した設定を表示する。
    mo.md(
        "\n".join(
            [
                "## 2. 実行設定（確定値）",
                f"- train years: `{resolved_cfg.train_year_start}` - `{resolved_cfg.train_year_end}`",
                f"- test year: `{resolved_cfg.test_year}`",
                f"- feature set: `{resolved_cfg.feature_set_name}`",
                f"- main parquet: `{resolved_cfg.main_parquet_path}`",
                f"- db url: `{resolved_cfg.db_url}`",
                f"- umaren odds table: `{resolved_cfg.umaren_odds_table}`",
                f"- min expected return: `{resolved_cfg.min_expected_return:.2f}`",
                f"- max top-N sweep: `{resolved_cfg.max_top_n}`",
            ]
        )
    )
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: データ読み込みセクション見出しを表示する。
    mo.md("""
    ## 3. データ読み込み
    """)
    return


@app.cell
def _(Path, pd, resolved_cfg, shlex):
    # セル概要: 学習用 parquet を読み込む。
    cache_path = Path(resolved_cfg.main_parquet_path)
    if not cache_path.exists():
        export_cmd = " ".join(
            [
                "scripts/refresh_analysis_cache.sh",
                "--skip-dbt",
                "--skip-odds",
                "--train-year-start",
                str(resolved_cfg.train_year_start),
                "--test-year",
                str(resolved_cfg.test_year),
                "--main-output",
                shlex.quote(str(cache_path)),
            ]
        )
        raise ValueError(
            "Main parquet not found.\n"
            f"missing_path={cache_path}\n"
            f"run_command={export_cmd}"
        )

    df_main = pd.read_parquet(cache_path)
    df_main.head(1)
    return (df_main,)


@app.cell
def _(df_main, pd):
    # セル概要: 学習 target を `is_top2` として追加する。
    df_feat = df_main.copy()
    held_dt = pd.to_datetime(df_feat["held_date"], errors="coerce")
    if held_dt.isna().any():
        raise ValueError(f"held_date conversion failed: {int(held_dt.isna().sum())} rows")

    result_order = pd.to_numeric(df_feat["result_order"], errors="coerce")
    if result_order.isna().any():
        raise ValueError(f"result_order conversion failed: {int(result_order.isna().sum())} rows")

    df_feat["held_year"] = held_dt.dt.year.astype("int64")
    df_feat["is_top2"] = (result_order.astype(int) <= 2).astype(int)
    df_feat["race_id"] = df_feat["race_id"].astype(str)

    summary_df = pd.DataFrame(
        [
            {
                "rows": int(len(df_feat)),
                "races": int(df_feat["race_id"].nunique()),
                "positive_rate": float(df_feat["is_top2"].mean()),
            }
        ]
    )
    summary_df
    return (df_feat,)


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 学習データ作成セクション見出しを表示する。
    mo.md("""
    ## 4. 学習データ作成
    """)
    return


@app.cell
def _(df_feat, notebook_feature_config, resolved_cfg):
    # セル概要: feature set を解決する。
    from harp.core.training import build_binary_dataset

    _, feature_names, cat_features = notebook_feature_config.resolve_feature_set(
        feature_set_name=resolved_cfg.feature_set_name,
        registry_path=resolved_cfg.registry_path,
    )

    ds = build_binary_dataset(
        df=df_feat,
        feature_names=feature_names,
        cat_features=cat_features,
        target_col="is_top2",
        train_year_start=int(resolved_cfg.train_year_start),
        train_year_end=int(resolved_cfg.train_year_end),
        test_year=int(resolved_cfg.test_year),
    )
    return (ds,)


@app.cell
def _(ds, mo):
    # セル概要: split サイズを表示する。
    mo.md(
        "\n".join(
            [
                "train / val / test split",
                f"- train: `{ds.X_tr.shape}`",
                f"- val: `{ds.X_val.shape}`",
                f"- test: `{ds.X_test.shape}`",
            ]
        )
    )
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: モデル学習セクション見出しを表示する。
    mo.md("""
    ## 5. モデル学習
    """)
    return


@app.cell
def _(ds, lgb, resolved_cfg):
    # セル概要: 複勝と同じパラメータで LightGBM を学習する。
    from harp.core.training import train_binary_lgbm

    model_params = {
        "objective": "binary",
        "n_estimators": 1000,
        "learning_rate": 0.03,
        "num_leaves": 15,
        "max_depth": 4,
        "subsample": 0.8,
        "colsample_bytree": 0.6,
        "min_child_samples": 200,
        "min_split_gain": 0.01,
        "reg_alpha": 0.0,
        "reg_lambda": 0.0,
        "random_state": int(resolved_cfg.global_seed),
        "bagging_seed": int(resolved_cfg.global_seed),
        "feature_fraction_seed": int(resolved_cfg.global_seed),
        "data_random_seed": int(resolved_cfg.global_seed),
        "deterministic": True,
        "force_col_wise": True,
        "n_jobs": 6,
        "verbosity": -1,
    }
    fit_kwargs = {
        "eval_set": [(ds.X_val, ds.y_val)],
        "eval_metric": "binary_logloss",
        "callbacks": [
            lgb.early_stopping(100, verbose=True),
            lgb.log_evaluation(period=200),
        ],
    }

    train_result = train_binary_lgbm(ds=ds, model_params=model_params, fit_kwargs=fit_kwargs)
    return (train_result,)


@app.cell(hide_code=True)
def _(mo):
    # セル概要: calibration と race 内制約のセクション見出しを表示する。
    mo.md("""
    ## 6. Platt calibration と Race 内制約
    """)
    return


@app.cell
def _(df_feat, ds, np, pd, train_result):
    # セル概要: test set の raw 予測とメタ情報を作る。
    raw_test_proba = train_result.model.predict_proba(ds.X_test)[:, 1].astype(float)

    df_test_meta = df_feat.loc[
        ds.X_test.index,
        ["race_id", "held_date", "horse_number", "horse_name", "j_odds_tansho"],
    ].copy()
    df_test_meta["race_id"] = df_test_meta["race_id"].astype(str)
    df_test_meta["held_date"] = pd.to_datetime(df_test_meta["held_date"], errors="coerce")
    df_test_meta["horse_number"] = df_test_meta["horse_number"].astype(int)
    df_test_meta["horse_name"] = df_test_meta["horse_name"].astype("string")
    df_test_meta["j_odds_tansho"] = df_test_meta["j_odds_tansho"].astype(float)

    np.clip(raw_test_proba[:5], 0.0, 1.0)
    return df_test_meta, raw_test_proba


@app.cell
def _(df_feat, df_test_meta, ds, raw_test_proba, resolved_cfg, train_result):
    # セル概要: Platt calibration を当てる。
    from harp.core.training import apply_platt_logodds, fit_platt_logodds_oof

    platt_info = fit_platt_logodds_oof(
        model=train_result.model,
        ds=ds,
        df_meta=df_feat,
        odds_col="j_odds_tansho",
        train_year_start=int(resolved_cfg.train_year_start),
        train_year_end=int(resolved_cfg.train_year_end),
        valid_years_back=5,
        eps=1e-12,
    )

    platt_test_proba = apply_platt_logodds(
        base_proba=raw_test_proba,
        payload={
            "calibration": {
                "method": "platt_logodds",
                "params": platt_info,
            }
        },
        df_feat=df_test_meta,
        odds_col="j_odds_tansho",
    ).astype(float)
    return (platt_test_proba,)


@app.cell
def _(df_test_meta, np, pd, platt_test_proba, raw_test_proba):
    # セル概要: 各 race の確率和を 2 に寄せる logit shift を適用する。
    from harp.core.training import apply_logit_shift_grouped

    race_ids = df_test_meta["race_id"].astype(str).reset_index(drop=True)
    horse_count = race_ids.groupby(race_ids, dropna=False).transform("size").astype(float)
    k_rule = np.minimum(2.0, horse_count.to_numpy(dtype=float))
    k_by_group = (
        pd.DataFrame({"race_id": race_ids.to_numpy(dtype=object), "k_rule": k_rule})
        .groupby("race_id", dropna=False)["k_rule"]
        .first()
        .astype(float)
        .to_dict()
    )
    shifted_test_proba = apply_logit_shift_grouped(
        np.asarray(platt_test_proba, dtype=float),
        race_ids.to_numpy(dtype=object),
        k_by_group=k_by_group,
    ).astype(float)

    race_sum_check = pd.DataFrame(
        [
            {
                "variant": "raw",
                "mean_race_sum": float(pd.Series(raw_test_proba, index=race_ids.index).groupby(race_ids).sum().mean()),
            },
            {
                "variant": "platt",
                "mean_race_sum": float(
                    pd.Series(platt_test_proba, index=race_ids.index).groupby(race_ids).sum().mean()
                ),
            },
            {
                "variant": "platt_shift_top2",
                "mean_race_sum": float(
                    pd.Series(shifted_test_proba, index=race_ids.index).groupby(race_ids).sum().mean()
                ),
            },
        ]
    )
    return race_sum_check, shifted_test_proba


@app.cell(hide_code=True)
def _(mo):
    # セル概要: メトリクス評価セクション見出しを表示する。
    mo.md("""
    ## 7. AUC / LogLoss
    """)
    return


@app.cell
def _(ds, pd, platt_test_proba, raw_test_proba, shifted_test_proba):
    # セル概要: raw / Platt / race 内制約後のメトリクスを比較する。
    from harp.core.training.metrics import calc_binary_metrics

    raw_metrics = calc_binary_metrics(ds.y_test, raw_test_proba)
    platt_metrics = calc_binary_metrics(ds.y_test, platt_test_proba)
    shifted_metrics = calc_binary_metrics(ds.y_test, shifted_test_proba)

    metrics_df = pd.DataFrame(
        [
            {
                "variant": "raw",
                "auc": raw_metrics["auc"],
                "logloss": raw_metrics["logloss"],
            },
            {
                "variant": "platt",
                "auc": platt_metrics["auc"],
                "logloss": platt_metrics["logloss"],
            },
            {
                "variant": "platt_shift_top2",
                "auc": shifted_metrics["auc"],
                "logloss": shifted_metrics["logloss"],
            },
        ]
    )
    metrics_df
    return (metrics_df,)


@app.cell(hide_code=True)
def _(mo):
    # セル概要: メトリクスの読み方を補足する。
    mo.md("""
    ## 8. 読み方

    - `AUC` は高いほど、2着以内の馬を上位に寄せられている
    - `logloss` は低いほど、確率の出し方が素直で外し方も大きすぎない
    - `platt_shift_top2` は「Platt 後の確率を、各レースの合計 2 に合わせたもの」
    - ここではまず馬ごと確率の整合性を見る段階なので、利益指標や買い目 simulation はまだ入れていない
    """)
    return


@app.cell
def _(metrics_df, race_sum_check):
    # セル概要: script mode でも確認できるように要点を標準出力へ出す。
    print("metrics")
    print(metrics_df.to_string(index=False))
    print("race_sum_check")
    print(race_sum_check.to_string(index=False))
    return


@app.cell
def _(race_sum_check):
    # セル概要: race 内制約が効いているかを確認する。
    race_sum_check
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 馬連 pair 復元セクション見出しを表示する。
    mo.md("""
    ## 9. Max-Entropy の unordered pair model
    """)
    return


@app.cell
def _(np):
    # セル概要: `top2` 周辺確率から馬連 pair 確率を復元する helper を定義する。
    def reconstruct_umaren_pair_probs_maxent(
        p_top2: np.ndarray,
        *,
        tol: float = 1e-10,
        max_iter: int = 20000,
    ) -> tuple[np.ndarray, np.ndarray, int]:
        p = np.asarray(p_top2, dtype=float).reshape(-1)
        if p.size < 2:
            raise ValueError("At least two horses are required to reconstruct umaren probabilities.")
        if not np.isfinite(p).all():
            raise ValueError("p_top2 must contain only finite values.")
        if (p < 0.0).any():
            raise ValueError("p_top2 must be non-negative.")

        total = float(p.sum())
        if total <= 0.0:
            raise ValueError("sum(p_top2) must be positive.")
        if abs(total - 2.0) > 1e-8:
            p = p * (2.0 / total)

        n = p.size
        if n == 2:
            pair_probs = np.array([1.0], dtype=float)
            marginals = np.array([1.0, 1.0], dtype=float)
            return pair_probs, marginals, 0

        matrix = np.ones((n, n), dtype=float)
        np.fill_diagonal(matrix, 0.0)

        for iteration in range(1, max_iter + 1):
            for idx in range(n):
                current = float(matrix[idx].sum())
                if current <= 0.0:
                    raise RuntimeError("IPF reconstruction failed because an incident mass became zero.")
                factor = float(p[idx] / current)
                matrix[idx, :] *= factor
                matrix[:, idx] = matrix[idx, :]
                matrix[idx, idx] = 0.0

            row_sums = matrix.sum(axis=1)
            max_err = float(np.max(np.abs(row_sums - p)))
            if max_err <= tol:
                break
        else:
            raise RuntimeError("IPF reconstruction did not converge within max_iter.")

        upper_i, upper_j = np.triu_indices(n=n, k=1)
        pair_probs = matrix[upper_i, upper_j].astype(float)
        pair_total = float(pair_probs.sum())
        if pair_total <= 0.0:
            raise RuntimeError("Reconstructed pair probabilities sum to zero.")
        pair_probs = pair_probs / pair_total

        check_matrix = np.zeros_like(matrix)
        check_matrix[upper_i, upper_j] = pair_probs
        check_matrix[upper_j, upper_i] = pair_probs
        marginals = check_matrix.sum(axis=1).astype(float)
        return pair_probs, marginals, int(iteration)

    return (reconstruct_umaren_pair_probs_maxent,)


@app.cell
def _(
    df_test_meta,
    np,
    pd,
    reconstruct_umaren_pair_probs_maxent,
    shifted_test_proba,
):
    # セル概要: test race ごとに馬連 pair 確率 DataFrame を構築する。
    df_top2_test = df_test_meta.copy().reset_index(drop=True)
    df_top2_test["p_top2"] = pd.Series(shifted_test_proba, dtype="float64")

    pair_rows: list[dict[str, object]] = []
    diag_rows: list[dict[str, object]] = []

    for race_id, race_df in df_top2_test.groupby("race_id", sort=False):
        race_local = race_df.sort_values("horse_number").reset_index(drop=True)
        probs = race_local["p_top2"].to_numpy(dtype=float)
        pair_probs, restored_marginals, n_iter = reconstruct_umaren_pair_probs_maxent(probs)

        horse_numbers = race_local["horse_number"].to_numpy(dtype=int)
        horse_names = race_local["horse_name"].astype(str).to_numpy(dtype=object)
        held_date = race_local["held_date"].iloc[0]

        pair_idx = 0
        for idx_1 in range(len(race_local)):
            for idx_2 in range(idx_1 + 1, len(race_local)):
                horse_number_1 = int(horse_numbers[idx_1])
                horse_number_2 = int(horse_numbers[idx_2])
                pair_rows.append(
                    {
                        "race_id": str(race_id),
                        "held_date": held_date,
                        "horse_number_1": horse_number_1,
                        "horse_number_2": horse_number_2,
                        "pair_key": f"{horse_number_1:02d}-{horse_number_2:02d}",
                        "horse_name_1": str(horse_names[idx_1]),
                        "horse_name_2": str(horse_names[idx_2]),
                        "p_top2_1": float(probs[idx_1]),
                        "p_top2_2": float(probs[idx_2]),
                        "umaren_prob": float(pair_probs[pair_idx]),
                        "prob_source": "platt_shift_top2_maxent",
                    }
                )
                pair_idx += 1

        diag_rows.append(
            {
                "race_id": str(race_id),
                "held_date": held_date,
                "num_horses": int(len(race_local)),
                "sum_p_top2": float(probs.sum()),
                "sum_umaren_prob": float(pair_probs.sum()),
                "max_marginal_abs_error": float(np.max(np.abs(restored_marginals - probs))),
                "ipf_iterations": int(n_iter),
            }
        )

    df_umaren_prob = pd.DataFrame(pair_rows).sort_values(
        ["race_id", "umaren_prob", "horse_number_1", "horse_number_2"],
        ascending=[True, False, True, True],
    ).reset_index(drop=True)
    df_umaren_prob["pair_rank"] = (
        df_umaren_prob.groupby("race_id", sort=False)["umaren_prob"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    umaren_reconstruction_diag = pd.DataFrame(diag_rows).sort_values("race_id").reset_index(drop=True)
    return df_umaren_prob, umaren_reconstruction_diag


@app.cell(hide_code=True)
def _(mo):
    # セル概要: pair 確率 DataFrame の読み方を補足する。
    mo.md("""
    ## 10. 出力の使い方

    - `df_umaren_prob` は `race_id + horse_number_1 + horse_number_2` 粒度
    - `pair_key` も持つので、`fct_race_umaren_odds_result` と素直に join できる
    - `umaren_prob` は `platt_shift_top2` を入力にした max-entropy 復元結果
    - `pair_rank` はレース内の馬連確率順位
    """)
    return


@app.cell
def _(df_umaren_prob):
    # セル概要: odds join しやすい列だけを揃えた view を作る。
    df_umaren_prob_join_ready = df_umaren_prob[
        [
            "race_id",
            "held_date",
            "horse_number_1",
            "horse_number_2",
            "pair_key",
            "horse_name_1",
            "horse_name_2",
            "umaren_prob",
            "pair_rank",
            "prob_source",
        ]
    ].copy()
    return (df_umaren_prob_join_ready,)


@app.cell
def _(df_umaren_prob):
    # セル概要: 後続 simulation の基点になる pair 確率表を表示する。
    df_umaren_prob.head(20)
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: DB odds join と simulation セクション見出しを表示する。
    mo.md("""
    ## 11. 10分前オッズで期待値 simulation
    """)
    return


@app.cell
def _(re, read_sql_df, resolved_cfg):
    # セル概要: DB から馬連 10分前 odds / 払戻を取得する。
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", resolved_cfg.umaren_odds_table):
        raise ValueError("umaren_odds_table must contain only letters, digits, underscore, and dots.")

    sql = f"""
        select
            cast(race_id as text) as race_id,
            horse_number_1::int as horse_number_1,
            horse_number_2::int as horse_number_2,
            pair_key::text as pair_key,
            odds_snapshot_time_10min,
            odds_popularity_10min::int as odds_popularity_10min,
            odds_umaren_10min::float8 as odds_umaren_10min,
            pay_umaren::float8 as pay_umaren,
            pay_popularity::int as pay_popularity
        from {resolved_cfg.umaren_odds_table}
        where cast(race_id as text) like :race_prefix
          and odds_umaren_10min is not null
    """
    df_umaren_odds = read_sql_df(
        sql,
        params={"race_prefix": f"{int(resolved_cfg.test_year)}%"},
        db_url=resolved_cfg.db_url,
    ).copy()

    if df_umaren_odds.empty:
        raise ValueError("No umaren odds rows were returned from DB for the selected test year.")

    df_umaren_odds["race_id"] = df_umaren_odds["race_id"].astype(str)
    df_umaren_odds["horse_number_1"] = df_umaren_odds["horse_number_1"].astype(int)
    df_umaren_odds["horse_number_2"] = df_umaren_odds["horse_number_2"].astype(int)
    df_umaren_odds["pair_key"] = df_umaren_odds["pair_key"].astype(str)
    df_umaren_odds["odds_umaren_10min"] = df_umaren_odds["odds_umaren_10min"].astype(float)
    df_umaren_odds["pay_umaren"] = df_umaren_odds["pay_umaren"].fillna(0.0).astype(float)
    return (df_umaren_odds,)


@app.cell
def _(df_umaren_odds, df_umaren_prob_join_ready, resolved_cfg):
    # セル概要: pair 確率と DB odds を結合し、simulation 用の評価テーブルを作る。
    df_umaren_eval = df_umaren_prob_join_ready.merge(
        df_umaren_odds,
        on=["race_id", "horse_number_1", "horse_number_2", "pair_key"],
        how="inner",
        validate="one_to_one",
    ).copy()

    if df_umaren_eval.empty:
        raise ValueError("Join between pair probabilities and umaren odds returned no rows.")

    race_settled = (
        df_umaren_eval.groupby("race_id", sort=False)["pay_umaren"]
        .transform("max")
        .gt(0.0)
    )
    df_umaren_eval = df_umaren_eval.loc[race_settled].copy()

    if df_umaren_eval.empty:
        raise ValueError("No settled races remained after filtering on pay_umaren.")

    df_umaren_eval["expected_return_10min"] = (
        df_umaren_eval["umaren_prob"] * df_umaren_eval["odds_umaren_10min"]
    )
    df_umaren_eval["expected_profit_10min"] = df_umaren_eval["expected_return_10min"] - 1.0
    df_umaren_eval["is_hit"] = df_umaren_eval["pay_umaren"].gt(0.0)
    df_umaren_eval["realized_return"] = df_umaren_eval["pay_umaren"] / 100.0
    df_umaren_eval["realized_profit"] = df_umaren_eval["realized_return"] - 1.0
    df_umaren_eval["is_bet_ev"] = df_umaren_eval["expected_return_10min"].ge(
        float(resolved_cfg.min_expected_return)
    )

    df_umaren_ev_bets = (
        df_umaren_eval.loc[df_umaren_eval["is_bet_ev"]]
        .sort_values(
            ["race_id", "expected_return_10min", "umaren_prob"],
            ascending=[True, False, False],
        )
        .reset_index(drop=True)
    )
    return df_umaren_ev_bets, df_umaren_eval


@app.cell
def _(df_umaren_ev_bets, df_umaren_eval, pd, resolved_cfg):
    # セル概要: EV > threshold の単純買い成績を集計する。
    coverage = pd.DataFrame(
        [
            {
                "num_pair_rows_model": int(len(df_umaren_eval)),
                "num_races_model": int(df_umaren_eval["race_id"].nunique()),
                "num_pair_rows_bet": int(len(df_umaren_ev_bets)),
                "num_races_bet": int(df_umaren_ev_bets["race_id"].nunique()),
                "bet_rate": float(df_umaren_ev_bets.shape[0] / df_umaren_eval.shape[0]),
                "avg_pairs_bet_per_race": float(
                    df_umaren_ev_bets.shape[0] / max(df_umaren_eval["race_id"].nunique(), 1)
                ),
            }
        ]
    )

    if df_umaren_ev_bets.empty:
        sim_summary = pd.DataFrame(
            [
                {
                    "strategy": f"expected_return>={float(resolved_cfg.min_expected_return):.2f}",
                    "num_bets": 0,
                    "num_races": 0,
                    "hit_rate": 0.0,
                    "avg_expected_return": 0.0,
                    "avg_odds_10min": 0.0,
                    "total_return": 0.0,
                    "total_profit": 0.0,
                    "roi": 0.0,
                    "profit_roi": 0.0,
                }
            ]
        )
    else:
        total_bets = float(len(df_umaren_ev_bets))
        total_return = float(df_umaren_ev_bets["realized_return"].sum())
        total_profit = float(df_umaren_ev_bets["realized_profit"].sum())
        sim_summary = pd.DataFrame(
            [
                {
                    "strategy": f"expected_return>={float(resolved_cfg.min_expected_return):.2f}",
                    "num_bets": int(total_bets),
                    "num_races": int(df_umaren_ev_bets["race_id"].nunique()),
                    "hit_rate": float(df_umaren_ev_bets["is_hit"].mean()),
                    "avg_expected_return": float(df_umaren_ev_bets["expected_return_10min"].mean()),
                    "avg_odds_10min": float(df_umaren_ev_bets["odds_umaren_10min"].mean()),
                    "total_return": total_return,
                    "total_profit": total_profit,
                    "roi": float(total_return / total_bets),
                    "profit_roi": float(total_profit / total_bets),
                }
            ]
        )

    ev_diag = (
        df_umaren_eval["expected_return_10min"]
        .describe(percentiles=[0.5, 0.8, 0.9, 0.95, 0.99])
        .rename("expected_return_10min")
        .to_frame()
        .reset_index()
        .rename(columns={"index": "stat"})
    )
    return coverage, ev_diag, sim_summary


@app.cell
def _(df_umaren_eval, pd, resolved_cfg):
    # セル概要: race ごとの期待値上位 TOP n を買う戦略を sweep する。
    max_top_n = min(int(resolved_cfg.max_top_n), int(df_umaren_eval["pair_rank"].max()))
    if max_top_n < 1:
        raise ValueError("No valid pair ranks were found for top-N sweep.")

    ranked = df_umaren_eval.copy()
    ranked["ev_rank_in_race"] = (
        ranked.groupby("race_id", sort=False)["expected_return_10min"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    rows: list[dict[str, object]] = []
    for top_n in range(1, max_top_n + 1):
        picked = ranked.loc[ranked["ev_rank_in_race"].le(top_n)].copy()
        _total_bets = float(len(picked))
        _total_return = float(picked["realized_return"].sum())
        _total_profit = float(picked["realized_profit"].sum())
        rows.append(
            {
                "top_n": int(top_n),
                "num_bets": int(_total_bets),
                "num_races": int(picked["race_id"].nunique()),
                "hit_rate": float(picked["is_hit"].mean()),
                "avg_expected_return": float(picked["expected_return_10min"].mean()),
                "avg_odds_10min": float(picked["odds_umaren_10min"].mean()),
                "total_return": _total_return,
                "total_profit": _total_profit,
                "roi": float(_total_return / _total_bets),
                "profit_roi": float(_total_profit / _total_bets),
            }
        )

    top_n_sweep = pd.DataFrame(rows)
    best_top_n_by_roi = (
        top_n_sweep.sort_values(["roi", "top_n"], ascending=[False, True]).head(10).reset_index(drop=True)
    )
    return best_top_n_by_roi, top_n_sweep


@app.cell(hide_code=True)
def _(mo):
    # セル概要: simulation 指標の読み方を説明する。
    mo.md("""
    ## 12. ROI の見方

    - `expected_return_10min = umaren_prob × odds_umaren_10min`
    - 今回の単純戦略は `expected_return_10min >= threshold` の買い目を全部 1 点買い
    - `top_n_sweep` は各レースで `expected_return_10min` 上位 `n` 件を 1 点ずつ買う戦略
    - `roi` は `total_return / num_bets`
    - `profit_roi` は `total_profit / num_bets = roi - 1`
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: pair 確率の calibration セクション見出しを表示する。
    mo.md("""
    ## 13. 馬連確率の Calibration
    """)
    return


@app.cell
def _(df_umaren_eval, np, pd):
    # セル概要: pair 確率の calibration table と rank 別集計を作る。
    from harp.core.training.metrics import calc_binary_metrics as _calc_binary_metrics

    df_calib = df_umaren_eval.copy()
    df_calib["y_hit"] = df_calib["is_hit"].astype(int)

    pair_metrics_raw = _calc_binary_metrics(
        df_calib["y_hit"].to_numpy(dtype=int),
        df_calib["umaren_prob"].to_numpy(dtype=float),
    )
    brier = float(
        np.mean((df_calib["umaren_prob"].to_numpy(dtype=float) - df_calib["y_hit"].to_numpy(dtype=float)) ** 2)
    )

    num_bins = min(10, int(df_calib["umaren_prob"].nunique()))
    if num_bins >= 2:
        bin_labels = [f"q{idx:02d}" for idx in range(1, num_bins + 1)]
        df_calib["prob_bin"] = pd.qcut(
            df_calib["umaren_prob"],
            q=num_bins,
            labels=bin_labels,
            duplicates="drop",
        )
    else:
        df_calib["prob_bin"] = "q01"

    calibration_table = (
        df_calib.groupby("prob_bin", observed=False, dropna=False)
        .agg(
            count=("y_hit", "size"),
            hits=("y_hit", "sum"),
            mean_pred=("umaren_prob", "mean"),
            empirical=("y_hit", "mean"),
            mean_odds_10min=("odds_umaren_10min", "mean"),
        )
        .reset_index()
    )
    calibration_table["abs_gap"] = (
        calibration_table["mean_pred"] - calibration_table["empirical"]
    ).abs()
    calibration_table["ece_weight"] = calibration_table["count"] / calibration_table["count"].sum()

    ece = float((calibration_table["abs_gap"] * calibration_table["ece_weight"]).sum())

    pair_calibration_summary = pd.DataFrame(
        [
            {
                "auc": float(pair_metrics_raw["auc"]),
                "logloss": float(pair_metrics_raw["logloss"]),
                "brier": brier,
                "ece": ece,
                "num_pairs": int(len(df_calib)),
                "num_races": int(df_calib["race_id"].nunique()),
                "base_rate": float(df_calib["y_hit"].mean()),
                "mean_pred": float(df_calib["umaren_prob"].mean()),
            }
        ]
    )

    rank_limit = min(10, int(df_calib["pair_rank"].max()))
    calibration_by_rank = (
        df_calib.loc[df_calib["pair_rank"].le(rank_limit)]
        .groupby("pair_rank", sort=True)
        .agg(
            count=("y_hit", "size"),
            hits=("y_hit", "sum"),
            mean_pred=("umaren_prob", "mean"),
            empirical=("y_hit", "mean"),
            mean_odds_10min=("odds_umaren_10min", "mean"),
            mean_expected_return_10min=("expected_return_10min", "mean"),
        )
        .reset_index()
    )
    calibration_by_rank["abs_gap"] = (
        calibration_by_rank["mean_pred"] - calibration_by_rank["empirical"]
    ).abs()

    calibration_table["prob_bin"] = calibration_table["prob_bin"].astype(str)
    return calibration_by_rank, calibration_table, pair_calibration_summary


@app.cell(hide_code=True)
def _(mo):
    # セル概要: calibration 指標の読み方を説明する。
    mo.md("""
    ## 14. 読み方

    - `base_rate` は全 pair の実際の的中率で、理論上はだいたい `1 / pair数`
    - `mean_pred` と `base_rate` が近いかで、全体の確率スケール感をざっくり見られる
    - `ECE` は bin ごとの予測確率と実測的中率のズレを件数重みでまとめたもの
    - `calibration_table` は確率帯ごとのズレ、`calibration_by_rank` はレース内順位ごとのズレを見るための表
    """)
    return


@app.cell
def _(coverage):
    # セル概要: odds join 後の coverage を確認する。
    coverage
    return


@app.cell
def _(pair_calibration_summary):
    # セル概要: pair-level calibration 指標を確認する。
    pair_calibration_summary
    return


@app.cell
def _(calibration_table):
    # セル概要: quantile bin ごとの calibration table を確認する。
    calibration_table
    return


@app.cell
def _(calibration_by_rank):
    # セル概要: pair rank ごとの calibration を確認する。
    calibration_by_rank
    return


@app.cell
def _(sim_summary):
    # セル概要: 単純 EV 買いの ROI 集計を確認する。
    sim_summary
    return


@app.cell
def _(top_n_sweep):
    # セル概要: race ごとの TOP n 買い sweep を確認する。
    top_n_sweep
    return


@app.cell
def _(best_top_n_by_roi):
    # セル概要: ROI 上位の TOP n を確認する。
    best_top_n_by_roi
    return


@app.cell
def _(df_umaren_ev_bets):
    # セル概要: 実際に買われた pair を確認する。
    df_umaren_ev_bets.head(20)
    return


@app.cell
def _(df_umaren_eval):
    # セル概要: 期待値の高い pair を確認する。
    df_umaren_eval[
        [
            "race_id",
            "pair_key",
            "umaren_prob",
            "odds_umaren_10min",
            "expected_return_10min",
            "pay_umaren",
            "realized_return",
        ]
    ].sort_values(
        ["expected_return_10min", "umaren_prob"],
        ascending=[False, False],
    ).head(20)
    return


@app.cell
def _(ev_diag):
    # セル概要: 期待値分布を確認する。
    ev_diag
    return


@app.cell
def _(umaren_reconstruction_diag):
    # セル概要: pair 復元の整合性を確認する。
    umaren_reconstruction_diag.describe(include="all")
    return


@app.cell
def _(
    best_top_n_by_roi,
    calibration_by_rank,
    calibration_table,
    coverage,
    df_umaren_ev_bets,
    df_umaren_eval,
    df_umaren_prob,
    ev_diag,
    pair_calibration_summary,
    sim_summary,
    top_n_sweep,
    umaren_reconstruction_diag,
):
    # セル概要: script mode でも pair 復元と simulation の要点を標準出力へ出す。
    print("umaren_reconstruction_diag")
    print(
        umaren_reconstruction_diag[
            [
                "num_horses",
                "sum_p_top2",
                "sum_umaren_prob",
                "max_marginal_abs_error",
                "ipf_iterations",
            ]
        ]
        .describe()
        .to_string()
    )
    print("df_umaren_prob_head")
    print(
        df_umaren_prob[
            [
                "race_id",
                "horse_number_1",
                "horse_number_2",
                "pair_key",
                "umaren_prob",
                "pair_rank",
            ]
        ]
        .head(20)
        .to_string(index=False)
    )
    print("coverage")
    print(coverage.to_string(index=False))
    print("pair_calibration_summary")
    print(pair_calibration_summary.to_string(index=False))
    print("calibration_table")
    print(calibration_table.to_string(index=False))
    print("calibration_by_rank")
    print(calibration_by_rank.to_string(index=False))
    print("sim_summary")
    print(sim_summary.to_string(index=False))
    print("top_n_sweep")
    print(top_n_sweep.to_string(index=False))
    print("best_top_n_by_roi")
    print(best_top_n_by_roi.to_string(index=False))
    print("ev_diag")
    print(ev_diag.to_string(index=False))
    print("df_umaren_ev_bets_head")
    if df_umaren_ev_bets.empty:
        print("EMPTY")
    else:
        print(
            df_umaren_ev_bets[
                [
                    "race_id",
                    "pair_key",
                    "umaren_prob",
                    "odds_umaren_10min",
                    "expected_return_10min",
                    "pay_umaren",
                    "realized_return",
                ]
            ]
            .head(20)
            .to_string(index=False)
        )
    print("df_umaren_eval_top_expected_return")
    print(
        df_umaren_eval[
            [
                "race_id",
                "pair_key",
                "umaren_prob",
                "odds_umaren_10min",
                "expected_return_10min",
                "pay_umaren",
                "realized_return",
            ]
        ]
        .sort_values(["expected_return_10min", "umaren_prob"], ascending=[False, False])
        .head(20)
        .to_string(index=False)
    )
    return


if __name__ == "__main__":
    app.run()
