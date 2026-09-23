from harp.core.nn.prediction import NnPredictor
from harp.interface.ports.nn_training_ports import NnModelStorePort


def load_nn_predictor(run_id: str, model_store: NnModelStorePort, *, device: str = "cpu",
                      checkpoint_id: str | None = None) -> NnPredictor:
    saved = model_store.load_checkpoint(run_id, checkpoint_id)
    return NnPredictor.from_weights(saved.preprocessing, saved.recipe.model, saved.checkpoint["best_weights"],
                                     saved.metadata["history_length"], device)
