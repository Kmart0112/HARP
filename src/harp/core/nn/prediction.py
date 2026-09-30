from dataclasses import dataclass

from .contracts import NnRaceInputs
from .dataset import NnRaceDataset
from .networks.factory import build_nn_network
from .preprocessing import NnPreprocessingState
from .tensor_batch import NnInputSpec
from .training import evaluate_nn


@dataclass(frozen=True)
class NnPredictor:
    model: object
    preprocessing: NnPreprocessingState
    history_length: int
    device: str
    task: str = "place"

    @classmethod
    def from_weights(cls, preprocessing, config, weights, history_length, device, *, task="place", auxiliary_rank=None,
                     auxiliary_odds=None):
        model = build_nn_network(NnInputSpec.from_preprocessing(preprocessing), config,
                                 rank_auxiliary=auxiliary_rank is not None, odds_auxiliary=auxiliary_odds is not None).to(device)
        model.load_state_dict(weights, strict=True)
        model.eval()
        return cls(model, preprocessing, history_length, device, task)

    def predict(self, inputs: NnRaceInputs, *, batch_size: int = 32):
        dataset = NnRaceDataset(inputs, self.preprocessing, self.history_length, task=self.task)
        return evaluate_nn(self.model, dataset, batch_size=batch_size, device=self.device).predictions
