from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st


APP_TITLE = "Outputs CSV Viewer"
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV_PATH = WORKSPACE_ROOT / "pipeline" / "outputs" / "edge_candidates.csv"


def _discover_output_dirs(root: Path) -> list[Path]:
	candidates = [root / "pipeline" / "outputs"]
	return [p for p in candidates if p.exists() and p.is_dir()]


def _list_csv_files(output_dir: Path) -> list[Path]:
	return sorted(output_dir.glob("*.csv"))


@st.cache_data(show_spinner=False)
def _load_csv(file_path: Path) -> pd.DataFrame:
	return pd.read_csv(file_path)


def main() -> None:
	st.set_page_config(page_title=APP_TITLE, layout="wide")
	st.title(APP_TITLE)

	output_dirs = _discover_output_dirs(WORKSPACE_ROOT)
	if not output_dirs:
		st.error("出力フォルダが見つかりません。")
		st.stop()

	dir_labels = [str(p.relative_to(WORKSPACE_ROOT)) for p in output_dirs]
	default_dir_label = None
	if DEFAULT_CSV_PATH.exists():
		try:
			default_dir_label = str(DEFAULT_CSV_PATH.parent.relative_to(WORKSPACE_ROOT))
		except ValueError:
			default_dir_label = None

	if default_dir_label in dir_labels:
		default_dir_index = dir_labels.index(default_dir_label)
	else:
		default_dir_index = 0

	selected_dir_label = st.sidebar.selectbox(
		"表示するoutputsフォルダ",
		dir_labels,
		index=default_dir_index,
	)
	selected_dir = output_dirs[dir_labels.index(selected_dir_label)]

	csv_files = _list_csv_files(selected_dir)
	if not csv_files:
		st.warning("CSVがありません。")
		st.stop()

	file_labels = [p.name for p in csv_files]
	if DEFAULT_CSV_PATH.exists() and DEFAULT_CSV_PATH.parent == selected_dir:
		default_file_label = DEFAULT_CSV_PATH.name
	else:
		default_file_label = None

	if default_file_label in file_labels:
		default_file_index = file_labels.index(default_file_label)
	else:
		default_file_index = 0

	selected_file_label = st.sidebar.selectbox(
		"CSVファイル",
		file_labels,
		index=default_file_index,
	)
	selected_file = csv_files[file_labels.index(selected_file_label)]

	with st.spinner("CSVを読み込み中..."):
		df = _load_csv(selected_file)

	st.caption(f"{selected_dir_label}/{selected_file.name}  |  rows: {len(df):,}  cols: {len(df.columns):,}")

	with st.expander("表示オプション", expanded=True):
		col1, col2, col3 = st.columns([1, 1, 2])
		with col1:
			max_rows = st.number_input("表示行数", min_value=10, max_value=5000, value=200, step=10)
		with col2:
			st.caption("indexは常に表示")
		with col3:
			search_text = st.text_input("全列検索（部分一致）", value="")

		reload_col, _ = st.columns([1, 3])
		with reload_col:
			if st.button("CSV再読み込み"):
				st.cache_data.clear()
				st.rerun()

		default_sort_cols = []
		reset_sort_cols = [
			col
			for col in ["held_date", "jyo_name", "rpund", "horse_number"]
			if col in df.columns
		]
		if "sort_columns" not in st.session_state:
			st.session_state["sort_columns"] = default_sort_cols

		sort_col1, sort_col2 = st.columns([3, 1])
		with sort_col1:
			sort_columns = st.multiselect(
				"ソート列（左から順）",
				options=list(df.columns),
				default=st.session_state["sort_columns"],
			)
		with sort_col2:
			if st.button("ソートリセット"):
				st.session_state["sort_columns"] = reset_sort_cols
				sort_columns = reset_sort_cols

	if search_text:
		mask = df.astype(str).apply(lambda s: s.str.contains(search_text, na=False))
		df_view = df[mask.any(axis=1)]
	else:
		df_view = df

	if sort_columns:
		df_view = df_view.sort_values(by=sort_columns, ascending=True, kind="mergesort")
	else:
		df_view = df_view.sort_index(ascending=True, kind="mergesort")

	df_display = df_view.head(int(max_rows))
	if "edge" in df_display.columns:
		def _highlight_edge(row: pd.Series) -> list[str]:
			try:
				value = float(row.get("edge"))
			except (TypeError, ValueError):
				value = None
			return ["background-color: #fff3bf" if value is not None and value >= 0.15 else "" for _ in row]

		styled = df_display.style.apply(_highlight_edge, axis=1)
		st.dataframe(styled, use_container_width=True, hide_index=False)
	else:
		st.dataframe(df_display, use_container_width=True, hide_index=False)

	st.download_button(
		label="CSVをダウンロード",
		data=selected_file.read_bytes(),
		file_name=selected_file.name,
		mime="text/csv",
	)


if __name__ == "__main__":
	main()
