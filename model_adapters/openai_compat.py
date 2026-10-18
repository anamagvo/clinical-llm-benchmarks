import os
from .base import ModelAdapter
from .streaming import consume_stream


class OpenAICompatAdapter(ModelAdapter):
    def generate(self, messages):
        headers = {}
        key_env = self.config.get("api_key_env")
        if key_env:
            key = os.environ.get(key_env)
            if not key:
                raise ValueError(f"Required environment variable {key_env} is not set")
            headers["Authorization"] = f"Bearer {key}"
        payload = {"model": self.config["model"], "messages": messages, "stream": True,
                   "temperature": self.config.get("temperature", 0),
                   "stream_options": {"include_usage": True}}
        payload.update(self.config.get("request_options", {}))
        payload["stream"] = True
        return consume_stream(self.config.get("base_url", "http://localhost:8000/v1").rstrip("/") + "/chat/completions",
                              payload, headers, "openai", self.config.get("timeout", [10, 300]))