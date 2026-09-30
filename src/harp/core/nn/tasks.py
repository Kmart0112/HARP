"""Task identity shared by Dataset preparation, training and prediction."""
from .contracts import NnInputContractError


def nn_target(task: str) -> str:
    if task not in ("place", "win"):
        raise NnInputContractError("NN task must be place or win")
    return "is_" + task
