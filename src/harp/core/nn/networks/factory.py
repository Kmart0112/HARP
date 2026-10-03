from ..config import NnModelConfig
from ..tensor_batch import NnInputSpec
from .race_history_set import RaceHistorySetTransformer


def build_nn_network(spec: NnInputSpec, config: NnModelConfig, *, rank_auxiliary: bool = False,
                     odds_auxiliary: bool = False) -> RaceHistorySetTransformer:
    """Build the saved architecture, including its history-token conditioning."""
    return RaceHistorySetTransformer(spec, config, rank_auxiliary=rank_auxiliary, odds_auxiliary=odds_auxiliary)
