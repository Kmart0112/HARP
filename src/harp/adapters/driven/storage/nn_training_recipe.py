import json
from pathlib import Path

import yaml

from harp.core.nn.contracts import NnInputContractError


class _UniqueKeysLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise NnInputContractError("duplicate or non-string NN recipe key")
        result[key] = loader.construct_object(value_node)
    return result


_UniqueKeysLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


class YamlNnTrainingRecipeReader:
    def load(self, path: str) -> dict:
        try:
            document = yaml.load(Path(path).read_text(), Loader=_UniqueKeysLoader)
        except yaml.YAMLError as exc:
            raise NnInputContractError("invalid NN recipe YAML") from exc
        if not isinstance(document, dict):
            raise NnInputContractError("NN recipe must be a mapping")
        return document

    def parse_overrides(self, values: tuple[str, ...]) -> dict:
        result = {}
        for value in values:
            key, separator, literal = value.partition("=")
            if not separator or not key or key in result:
                raise NnInputContractError("overrides require unique section.field=value entries")
            try:
                result[key] = json.loads(literal)
            except ValueError:
                # Bare names such as runtime.device=cpu remain ordinary strings.
                result[key] = literal
        return result
