from ..config import NnModelConfig
from ..tensor_batch import NnInputSpec
from .race_history_set import RaceHistorySetTransformer


def build_nn_network(spec: NnInputSpec, config: NnModelConfig) -> RaceHistorySetTransformer:
    """Architecture name is validated by the typed config; v1 is a Transformer."""
    return RaceHistorySetTransformer(spec, config)
