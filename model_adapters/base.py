from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Response:
    text: str = ""
    ttft_s: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    token_source: str = "unavailable"
    error: str | None = None
    interrupted: bool = False
    finish_reason: str | None = None


class ModelAdapter(ABC):
    def __init__(self, name, **config):
        self.name, self.config = name, config

    @abstractmethod
    def generate(self, messages: list[dict]) -> Response:
        """Return actual accumulated text, including partial text on errors."""