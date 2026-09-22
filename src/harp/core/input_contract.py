"""Model compatibility is expressed in domain meanings, not database names."""
from __future__ import annotations

from harp.core.odds import ODDS_CONTRACT_VERSION, OddsContractError, OddsPolicy

ODDS_FEATURE_VERSION = "1.0"


def require_model_input_contract(payload: dict, policy: OddsPolicy | None = None) -> dict:
    contract = payload.get("input_contract")
    if not isinstance(contract, dict):
        raise OddsContractError("legacy model has no input contract; retrain with an explicit odds policy")
    if (contract.get("odds_contract_version") != ODDS_CONTRACT_VERSION
            or contract.get("odds_feature_version") != ODDS_FEATURE_VERSION):
        raise OddsContractError("unsupported model input contract version")
    if contract.get("feature_names") != payload.get("feature_names"):
        raise OddsContractError("model feature names differ from its input contract")
    training = contract.get("training_odds_policy")
    if not isinstance(training, dict) or OddsPolicy(**training).mode != "pre_start":
        raise OddsContractError("model training odds policy must be pre_start")
    allowed = contract.get("allowed_prediction_policies")
    if not isinstance(allowed, list) or any(mode not in {"latest_before", "pre_start"} for mode in allowed):
        raise OddsContractError("invalid allowed prediction policies")
    if policy is not None:
        if policy.mode not in allowed:
            raise OddsContractError("model does not permit the requested prediction odds policy")
        if policy.max_age_seconds > training["max_age_seconds"]:
            raise OddsContractError("prediction odds freshness exceeds the model input contract")
        if training.get("require_availability") and not policy.require_availability:
            raise OddsContractError("model requires known availability times")
    return contract
