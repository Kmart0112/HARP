"""Pure calculations for generic entity-by-condition aptitude analysis."""

from .analysis import (
    PairConfirmationResult,
    PairScreenResult,
    confirm_pair,
    prepare_pair_frame,
    screen_pair,
)
from .empirical_bayes import (
    EmpiricalBayesFitResult,
    EmpiricalBayesInteractionModel,
    fit_empirical_bayes_interactions,
)
from .regularized_logistic import (
    InteractionLogisticModel,
    binary_brier_score,
    binary_log_loss,
    fit_regularized_interaction_logistic,
)
from .specs import (
    ConditionSpec,
    ConfirmationPolicy,
    EntitySpec,
    NumericRange,
    ObservationSchema,
    PairSpec,
    ScreeningPolicy,
)
from .time_validation import (
    BootstrapInterval,
    TimeFold,
    block_bootstrap_mean,
    build_expanding_window_folds,
    build_inner_tuning_split,
)
from .transforms import materialize_condition

__all__ = [
    "BootstrapInterval",
    "ConditionSpec",
    "ConfirmationPolicy",
    "EmpiricalBayesFitResult",
    "EmpiricalBayesInteractionModel",
    "EntitySpec",
    "InteractionLogisticModel",
    "NumericRange",
    "ObservationSchema",
    "PairConfirmationResult",
    "PairScreenResult",
    "PairSpec",
    "ScreeningPolicy",
    "TimeFold",
    "binary_brier_score",
    "binary_log_loss",
    "block_bootstrap_mean",
    "build_expanding_window_folds",
    "build_inner_tuning_split",
    "confirm_pair",
    "fit_empirical_bayes_interactions",
    "fit_regularized_interaction_logistic",
    "materialize_condition",
    "prepare_pair_frame",
    "screen_pair",
]
