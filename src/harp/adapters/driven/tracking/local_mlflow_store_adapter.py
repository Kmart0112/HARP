from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

from harp.interface.ports import MlflowStoreVerification


class LocalMlflowStoreAdapter:
    def resolve_local_store_dir(self, tracking_uri: str) -> str | None:
        parsed = urlparse(tracking_uri)
        if parsed.scheme == "file":
            return str(Path(unquote(parsed.path)).resolve())
        if parsed.scheme == "":
            return str(Path(tracking_uri).resolve())
        return None

    def verify_store_readable(self, tracking_uri: str) -> MlflowStoreVerification:
        import mlflow

        mlflow.set_tracking_uri(tracking_uri)
        client = mlflow.tracking.MlflowClient(tracking_uri=tracking_uri)
        experiments = client.search_experiments()
        return MlflowStoreVerification(
            experiment_names=tuple(sorted(str(experiment.name) for experiment in experiments)),
        )

    def detect_legacy_path_references(
        self,
        *,
        tracking_uri: str,
        legacy_store_dir: str,
    ) -> tuple[str, ...]:
        store_dir = self.resolve_local_store_dir(tracking_uri)
        if store_dir is None:
            return ()

        resolved_store_dir = Path(store_dir).resolve()
        resolved_legacy_dir = Path(legacy_store_dir).resolve()
        if resolved_store_dir == resolved_legacy_dir:
            return ()

        legacy_path = str(resolved_legacy_dir)
        legacy_uri = resolved_legacy_dir.as_uri()
        findings: list[str] = []
        for meta_path in sorted(resolved_store_dir.rglob("meta.yaml")):
            payload = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            artifact_location = str(payload.get("artifact_location", ""))
            artifact_uri = str(payload.get("artifact_uri", ""))
            if legacy_path in artifact_location or legacy_uri in artifact_location:
                findings.append(str(meta_path))
                continue
            if legacy_path in artifact_uri or legacy_uri in artifact_uri:
                findings.append(str(meta_path))
        return tuple(findings)

    def rewrite_meta_for_target(
        self,
        *,
        rel_path: str,
        source_text: str,
        target_store_dir: str,
    ) -> str:
        payload = yaml.safe_load(source_text)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid MLflow meta.yaml payload: {rel_path}")
        parts = Path(rel_path).parts
        target_root = Path(target_store_dir).resolve()
        if len(parts) == 2:
            payload["artifact_location"] = (target_root / parts[0]).as_uri()
        elif len(parts) == 3:
            payload["artifact_uri"] = (target_root / parts[0] / parts[1] / "artifacts").as_uri()
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
