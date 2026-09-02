# Analysis Docs

HARP の分析方法を、巨大な単一ドキュメントではなくテーマ別に分けて整理する。

## 入口

- [data_preparation.md](data_preparation.md): dbt と mart を使った分析データ作成
- [modeling_and_validation.md](modeling_and_validation.md): 予測モデル、校正、特徴量検証、SHAP
- [betting_decisions.md](betting_decisions.md): 確率予測を馬券判断に接続する考え方

## 基本方針

HARP では、予測精度と馬券判断を同じものとして扱わない。まず dbt で学習可能な特徴量テーブルを作り、Python 側でモデル性能と校正を検証し、その後にオッズや資金制約を踏まえて買う/買わないを判断する。

分析で得た再利用可能な知見は、詳細ログではなく「次に使える文章」として [../knowledge/README.md](../knowledge/README.md) に残す。
