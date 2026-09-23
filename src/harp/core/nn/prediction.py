from dataclasses import dataclass

from .contracts import NnRaceInputs
from .dataset import NnRaceDataset
from .preprocessing import NnPreprocessingState
from .networks.factory import build_nn_network
from .tensor_batch import NnInputSpec
from .training import evaluate_nn


@dataclass(frozen=True)
class NnPredictor:
    model: object
    preprocessing: NnPreprocessingState
    history_length: int
    device: str

    @classmethod
    def from_weights(cls, preprocessing, config, weights, history_length, device):
        model = build_nn_network(NnInputSpec.from_preprocessing(preprocessing), config).to(device)
        model.load_state_dict(weights, strict=True)
        model.eval()
        return cls(model, preprocessing, history_length, device)

    def predict(self, inputs: NnRaceInputs, *, batch_size: int = 32):
        dataset = NnRaceDataset(inputs, self.preprocessing, self.history_length)
        return evaluate_nn(self.model, dataset, batch_size=batch_size, device=self.device).predictions
