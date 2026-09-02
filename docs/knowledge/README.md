# ナレッジ

ここは、HARP で今まで分かったことを文章ベースでまとめる場所。実験ログ、設定テンプレート、registry の置き場ではなく、次の分析や実装で再利用できる「考え方」「経験則」「注意点」を残す。

## 置くもの

- 実験や調査から見えてきた再利用可能な結論
- 特徴量設計、モデル設計、買い方最適化の一般原則
- うまく効いた/効かなかった条件と、その解釈
- 次に同じテーマを触るときの見方や注意点

## 置かないもの

- 実験 run ごとの詳細ログ
- MLflow artifact の代替
- feature/model/betting の YAML registry
- 空のカード、将来用テンプレート、運用プレースホルダ
- 実装仕様や責務分離の正本

詳細な実験証跡は MLflow と `notebook/report`、設計判断は `docs/design`、運用手順は `docs/operations` に置く。

## ディレクトリ構成

- `foundations`: 長期的に使い回す一般原則
- `patterns`: 実験や分析から見えた経験則、テーマ別メモ

テンプレートや registry は知見本文ではないため、この公開ドキュメントには含めない。

## 書き方

1. 最初に「今の結論」を短く書く。
2. どんな条件で効いたか、効かなかったかを書く。
3. 解釈上の注意を書く。
4. 根拠になる notebook/report/MLflow run があればリンクする。
5. 数値の羅列ではなく、次に使う人が判断できる文章にする。

## 入口

- [foundations/index.md](foundations/index.md): 一般原則の索引
- [patterns/index.md](patterns/index.md): 経験則メモの索引
