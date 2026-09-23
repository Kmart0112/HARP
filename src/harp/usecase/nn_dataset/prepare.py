from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.dataset import PreparedNnDataset, prepare_nn_dataset, restore_nn_dataset
from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetRecipe

from .dto import NnDatasetDeps, PrepareNnDatasetRequest, PrepareNnDatasetResult


def run_prepare_nn_dataset_usecase(req: PrepareNnDatasetRequest, deps: NnDatasetDeps) -> PrepareNnDatasetResult:
    if req.input_dataset_id is not None:
        inputs = deps.input_store.load(req.input_dataset_id).inputs
    else:
        if deps.repository is None:
            raise NnInputContractError("DB input preparation requires an input repository")
        inputs = deps.repository.load_training_inputs(req.query)
    prepared = prepare_nn_dataset(inputs, req.config)
    input_id = req.input_dataset_id or deps.input_store.save(inputs, {"purpose": "nn_dataset"})
    recipe = NnPreparedDatasetRecipe(input_id, prepared.config, prepared.preprocessing, prepared.partitions)
    prepared_id = deps.prepared_store.save(recipe)
    return PrepareNnDatasetResult(input_id, prepared_id, prepared.summary)


def load_prepared_nn_dataset(prepared_dataset_id: str, deps: NnDatasetDeps) -> PreparedNnDataset:
    recipe = deps.prepared_store.load(prepared_dataset_id)
    inputs = deps.input_store.load(recipe.input_dataset_id).inputs
    return restore_nn_dataset(inputs, recipe.config, recipe.preprocessing, recipe.partitions)
