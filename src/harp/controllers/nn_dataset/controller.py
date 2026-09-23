from dataclasses import dataclass

from harp.core.nn.contracts import NnInputContractError, NnInputQuery
from harp.core.nn.split import NnDatasetConfig
from harp.usecase.nn_dataset.dto import PrepareNnDatasetRequest
from harp.usecase.nn_dataset.prepare import load_prepared_nn_dataset, run_prepare_nn_dataset_usecase

from .deps import build_nn_dataset_deps, load_nn_feature_contract


@dataclass(frozen=True)
class PrepareNnDatasetCommand:
    train_end_date: str
    validation_end_date: str
    history_length: int = 10
    input_dataset_id: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    max_races: int | None = None
    contract_path: str = "pipeline/config/nn_input_contract.json"


class NnDatasetController:
    def __init__(self, input_root: str, prepared_root: str, *, db_url: str | None = None):
        self.input_root, self.prepared_root, self.db_url = input_root, prepared_root, db_url

    def run(self, cmd: PrepareNnDatasetCommand):
        config = NnDatasetConfig(cmd.train_end_date, cmd.validation_end_date, cmd.history_length)
        contract, query = None, None
        if cmd.input_dataset_id is not None:
            if cmd.from_date is not None or cmd.to_date is not None or cmd.max_races is not None:
                raise NnInputContractError("saved input mode cannot also select dates or max_races")
        else:
            if self.db_url is None:
                raise NnInputContractError("DB input preparation requires database settings")
            contract = load_nn_feature_contract(cmd.contract_path)
            query = NnInputQuery(cmd.from_date, cmd.to_date, contract.pre_race_names, contract.history_result_names, cmd.max_races)
        req = PrepareNnDatasetRequest(config, cmd.input_dataset_id, query)
        with build_nn_dataset_deps(self.input_root, self.prepared_root,
                                   db_url=self.db_url if query is not None else None, contract=contract) as deps:
            return run_prepare_nn_dataset_usecase(req, deps)

    def load(self, prepared_dataset_id: str):
        with build_nn_dataset_deps(self.input_root, self.prepared_root) as deps:
            return load_prepared_nn_dataset(prepared_dataset_id, deps)
