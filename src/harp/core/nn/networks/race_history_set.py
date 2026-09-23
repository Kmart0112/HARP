import torch
from torch import nn

from ..config import NnModelConfig
from ..contracts import NnInputContractError
from ..tensor_batch import NnInputSpec, NnModelInputs
from .encoders import FeatureEncoder, MaskedTransformer


class RaceHistorySetTransformer(nn.Module):
    def __init__(self, spec: NnInputSpec, config: NnModelConfig):
        super().__init__()
        self.current_encoder = FeatureEncoder(len(spec.current_numeric), spec.current_categories, config)
        self.history_encoder = FeatureEncoder(len(spec.history_numeric), spec.history_categories, config, relative_count=2)
        self.history_token = nn.Parameter(torch.empty(1, 1, config.d_model))
        nn.init.normal_(self.history_token, std=.02)
        self.history_transformer = MaskedTransformer(config, config.history_layers)
        self.fusion = nn.Sequential(nn.Linear(config.d_model * 2, config.d_model), nn.LayerNorm(config.d_model), nn.GELU())
        self.race_transformer = MaskedTransformer(config, config.race_layers)
        self.head = nn.Linear(config.d_model, 1)

    def forward(self, inputs: NnModelInputs) -> torch.Tensor:
        valid = inputs.entrant_mask
        if valid.ndim != 2 or not valid.any(dim=1).all():
            raise NnInputContractError("each NN race must contain at least one real entrant")
        # Only real horses enter the encoders. Identity metadata/labels aren't in inputs.
        current = self.current_encoder(inputs.current_numeric[valid], inputs.current_numeric_missing[valid], inputs.current_categorical[valid])
        history_valid = inputs.history_mask[valid]
        # Sanitize padding before embedding lookup, projection, and attention.
        numeric = inputs.history_numeric[valid].masked_fill(~history_valid.unsqueeze(-1), 0)
        missing = inputs.history_numeric_missing[valid] & history_valid.unsqueeze(-1)
        categorical = inputs.history_categorical[valid].masked_fill(~history_valid.unsqueeze(-1), 0)
        relative = inputs.history_relative[valid].masked_fill(~history_valid.unsqueeze(-1), 0)
        history = self.history_encoder(numeric, missing, categorical, relative)
        token = self.history_token.expand(len(current), -1, -1)
        history = torch.cat((token, history), dim=1)
        token_valid = torch.ones((len(current), 1), dtype=torch.bool, device=valid.device)
        history = self.history_transformer(history, torch.cat((token_valid, history_valid), dim=1))[:, 0]
        combined = self.fusion(torch.cat((current, history), dim=-1))
        field = combined.new_zeros((*valid.shape, combined.shape[-1]))
        field[valid] = combined
        # No array-slot positional encoding: the field is permutation equivariant.
        result = self.head(self.race_transformer(field, valid)).squeeze(-1)
        return result.masked_fill(~valid, 0)
