from dataclasses import dataclass

from harp.core.nn.config import resolve_nn_training_recipe
from .deps import build_nn_recipe_reader, build_nn_train_deps, resolve_nn_device


@dataclass(frozen=True)
class NnTrainCommand:
    prepared_dataset_id: str
    recipe_path: str
    overrides: tuple[str, ...] = ()
    resume_run_id: str | None = None


class NnTrainController:
    def __init__(self, input_root: str, prepared_root: str, model_root: str, *,
                 provenance: dict, tracking_uri: str | None = None, tracking_experiment: str | None = None):
        self.input_root, self.prepared_root, self.model_root = input_root, prepared_root, model_root
        self.provenance, self.tracking_uri, self.tracking_experiment = provenance, tracking_uri, tracking_experiment

    def run(self, cmd: NnTrainCommand):
        import torch
        from harp.usecase.training.nn import run_nn_train_usecase
        from harp.usecase.training.nn_dto import NnTrainRequest

        reader = build_nn_recipe_reader()
        recipe = resolve_nn_training_recipe(reader.load(cmd.recipe_path), reader.parse_overrides(cmd.overrides))
        device = resolve_nn_device(recipe.runtime.device)
        request = NnTrainRequest(cmd.prepared_dataset_id, recipe, device, self.provenance,
                                 cmd.resume_run_id, self.tracking_experiment)
        deps = build_nn_train_deps(self.input_root, self.prepared_root, self.model_root, tracking_uri=self.tracking_uri)
        original_threads = torch.get_num_threads()
        try:
            torch.set_num_threads(recipe.runtime.num_threads)
            return run_nn_train_usecase(request, deps)
        finally:
            torch.set_num_threads(original_threads)

    def evaluate(self, run_id: str, *, split: str = "test", device: str = "cpu",
                 checkpoint_id: str | None = None, batch_size: int = 32):
        import torch
        from harp.usecase.training.nn import run_nn_evaluate_usecase
        from harp.usecase.training.nn_dto import NnEvaluateRequest

        deps = build_nn_train_deps(self.input_root, self.prepared_root, self.model_root)
        request = NnEvaluateRequest(run_id, resolve_nn_device(device), split, checkpoint_id, batch_size)
        original_threads = torch.get_num_threads()
        try:
            torch.set_num_threads(1)
            return run_nn_evaluate_usecase(request, deps)
        finally:
            torch.set_num_threads(original_threads)
