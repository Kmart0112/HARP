"""External JSON representation of the dbt-owned NN feature contract."""
import json
from pathlib import Path

from harp.core.nn.contracts import NnFeatureContract, NnFeatureField, NnInputContractError


def decode_nn_feature_contract(document: dict) -> NnFeatureContract:
    try:
        if set(document) != {"version", "pre_race", "history_results"}:
            raise ValueError
        return NnFeatureContract(
            pre_race=tuple(NnFeatureField(**field) for field in document["pre_race"]),
            history_results=tuple(NnFeatureField(**field) for field in document["history_results"]),
            version=document["version"],
        )
    except (TypeError, KeyError, ValueError) as exc:
        raise NnInputContractError("invalid NN feature contract document") from exc


class JsonNnFeatureContractReader:
    def load(self, path: str) -> NnFeatureContract:
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise NnInputContractError("invalid NN feature contract JSON") from exc
        return decode_nn_feature_contract(document)
