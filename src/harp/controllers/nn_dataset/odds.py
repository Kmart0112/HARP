from dataclasses import dataclass

from harp.usecase.nn_dataset.odds import (
    CaptureNnFinalOddsRequest,
    run_capture_nn_final_odds_usecase,
)

from .odds_deps import build_nn_odds_deps


@dataclass(frozen=True)
class CaptureNnFinalOddsCommand:
    prepared_dataset_id: str
    batch_size: int = 5000


class NnFinalOddsController:
    def __init__(self, *, input_root: str, prepared_root: str, output_root: str, db_url: str):
        self.input_root, self.prepared_root = input_root, prepared_root
        self.output_root, self.db_url = output_root, db_url

    def run(self, cmd: CaptureNnFinalOddsCommand):
        with build_nn_odds_deps(self.input_root, self.prepared_root, self.output_root,
                               db_url=self.db_url, batch_size=cmd.batch_size) as deps:
            return run_capture_nn_final_odds_usecase(CaptureNnFinalOddsRequest(cmd.prepared_dataset_id), deps)
