import json
import time
import requests
from .base import Response


def consume_stream(url, payload, headers, backend, timeout):
    result = Response()
    started = time.perf_counter()
    complete = False
    try:
        with requests.post(url, json=payload, headers=headers, stream=True,
                           timeout=tuple(timeout)) as response:
            response.raise_for_status()
            for raw in response.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8")
                if backend == "openai":
                    if not line.startswith("data:"):
                        continue
                    line = line[5:].strip()
                    if line == "[DONE]":
                        complete = True
                        break
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise ValueError("Inference server returned an error")
                if backend == "ollama":
                    piece = chunk.get("message", {}).get("content") or ""
                    if chunk.get("done"):
                        complete = True
                        result.input_tokens = chunk.get("prompt_eval_count")
                        result.output_tokens = chunk.get("eval_count")
                        result.finish_reason = chunk.get("done_reason")
                else:
                    choices = chunk.get("choices") or []
                    choice = choices[0] if choices else {}
                    piece = choice.get("delta", {}).get("content") or ""
                    if choice.get("finish_reason"):
                        result.finish_reason = choice["finish_reason"]
                    usage = chunk.get("usage") or {}
                    if usage:
                        result.input_tokens = usage.get("prompt_tokens")
                        result.output_tokens = usage.get("completion_tokens")
                if piece:
                    if result.ttft_s is None:
                        result.ttft_s = time.perf_counter() - started
                    result.text += piece
            if not complete:
                result.error = "Stream ended without completion marker"
    except KeyboardInterrupt:
        result.error, result.interrupted = "Interrupted by user", True
    except requests.HTTPError as exc:
        result.error = f"HTTP {exc.response.status_code if exc.response is not None else 'error'}"
    except Exception as exc:
        # Avoid persisting URLs or credentials contained in requests exceptions.
        result.error = f"{type(exc).__name__}: inference stream failed"
    if result.input_tokens is not None or result.output_tokens is not None:
        result.token_source = "provider"
    return result