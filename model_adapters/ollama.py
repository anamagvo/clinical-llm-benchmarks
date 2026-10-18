from .base import ModelAdapter
from .streaming import consume_stream


class OllamaAdapter(ModelAdapter):
    def generate(self, messages):
        payload = {"model": self.config["model"], "messages": messages, "stream": True,
                   "options": self.config.get("options", {"temperature": 0})}
        if self.config.get("format"):
            payload["format"] = self.config["format"]
        return consume_stream(self.config.get("base_url", "http://localhost:11434").rstrip("/") + "/api/chat",
                              payload, {}, "ollama", self.config.get("timeout", [10, 300]))