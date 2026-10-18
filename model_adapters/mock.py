import json
from .base import ModelAdapter, Response


class MockAdapter(ModelAdapter):
    def generate(self, messages):
        text = json.dumps({"reply": "Seit wann bestehen die Schmerzen? Haben Sie Allergien?",
                           "extracted": {}}, ensure_ascii=False)
        return Response(text=text, input_tokens=sum(len(m["content"].split()) for m in messages),
                        output_tokens=len(text.split()), ttft_s=0.0,
                        token_source="mock_estimate", finish_reason="mock")