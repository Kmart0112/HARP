import torch
from torch import nn

from ..config import NnModelConfig


class FeatureEncoder(nn.Module):
    """Separate embeddings per feature and per current/history vocabulary."""

    def __init__(self, numeric_count, categories, config: NnModelConfig, *, relative_count=0):
        super().__init__()
        self.embeddings = nn.ModuleList(nn.Embedding(size, config.categorical_embedding_dim, padding_idx=0)
                                        for _, size in categories)
        width = numeric_count * 2 + len(categories) * config.categorical_embedding_dim + relative_count
        self.projection = nn.Sequential(nn.Linear(width, config.d_model), nn.LayerNorm(config.d_model), nn.GELU())

    def forward(self, numeric, missing, categorical, relative=None):
        columns = [numeric, missing.to(numeric.dtype)]
        columns.extend(embedding(categorical[..., index]) for index, embedding in enumerate(self.embeddings))
        if relative is not None:
            columns.append(relative)
        return self.projection(torch.cat(columns, dim=-1))


class MaskedTransformer(nn.Module):
    def __init__(self, config: NnModelConfig, layers: int):
        super().__init__()
        # Construct independently, rather than cloning identical initialized layers.
        self.layers = nn.ModuleList(nn.TransformerEncoderLayer(
            d_model=config.d_model, nhead=config.attention_heads,
            dim_feedforward=config.feedforward_dim, dropout=config.dropout,
            activation="gelu", batch_first=True, norm_first=True,
        ) for _ in range(layers))
        self.norm = nn.LayerNorm(config.d_model)

    def forward(self, value, valid):
        # Masked query rows are zeroed too; they never become keys in later layers.
        value = value.masked_fill(~valid.unsqueeze(-1), 0)
        for layer in self.layers:
            value = layer(value, src_key_padding_mask=~valid, is_causal=False)
            value = value.masked_fill(~valid.unsqueeze(-1), 0)
        return self.norm(value).masked_fill(~valid.unsqueeze(-1), 0)
