from .base import ModelAdapter, Response
from .mock import MockAdapter
from .ollama import OllamaAdapter
from .openai_compat import OpenAICompatAdapter

REGISTRY = {"mock": MockAdapter, "ollama": OllamaAdapter, "openai_compat": OpenAICompatAdapter}


def get_adapter(config):
    config = dict(config)
    kind, name = config.pop("type"), config.pop("name")
    if kind not in REGISTRY:
        raise ValueError(f"Unknown adapter type: {kind}")
    return REGISTRY[kind](name, **config)