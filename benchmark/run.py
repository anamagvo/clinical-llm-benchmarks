import argparse
from datetime import datetime, timezone
from pathlib import Path
import time
import uuid
import yaml
from model_adapters import get_adapter
from model_adapters.base import Response
from .scenarios import load_scenarios
from .storage import append_record

DEFAULT_REPETITIONS = 1000


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def positive_repetitions(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("repetitions must be a positive integer")
    return value


def build_warmup_messages(scenarios):
    first_scenario = scenarios[0]
    if not first_scenario.patient_turns:
        raise ValueError(f"Scenario {first_scenario.id} has no patient turns for warm-up")
    first_turn = first_scenario.patient_turns[0]
    return (
        [{"role": "system", "content": first_scenario.system_prompt}]
        + list(first_scenario.context)
        + [{"role": "user", "content": first_turn["message"]}]
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Record workstation LLM responses; no scoring")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--output", help="New raw JSONL file (existing files are never overwritten)")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--warmup_repetitions", type=int)
    args = parser.parse_args(argv)
    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    repetitions = positive_repetitions(args.repetitions if args.repetitions is not None
                                      else config.get("repetitions", DEFAULT_REPETITIONS))
    models = [{"name": "mock-only", "type": "mock"}] if args.mock else config.get("models", [])
    if not models or len({m["name"] for m in models}) != len(models):
        raise ValueError("Configure at least one model with unique names")
    scenarios = load_scenarios(config_path.parent / config.get("scenarios_dir", "scenarios"))
    if len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError("Scenario IDs must be unique")
    adapters = [(m, get_adapter(m)) for m in models]
    warmup_messages = build_warmup_messages(scenarios)
    run_id = str(uuid.uuid4())
    output = Path(args.output) if args.output else config_path.parent / config.get("output_dir", "results") / f"raw-{run_id}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create prevents mixing experiments; fsync each later record.
    with output.open("x", encoding="utf-8"):
        pass
    append_record(output, {"record_type": "run", "schema_version": 1, "run_id": run_id,
                          "started_at": utc_now(), "repetitions": repetitions,
                          "models": [{"name": m["name"], "type": m["type"], "model": m.get("model"),
                                      "mock": m["type"] == "mock"} for m in models],
                          "scenario_ids": [s.id for s in scenarios]})
    print(f"Recording to {output}", flush=True)
    status = "complete"
    try:
            
        for model, adapter in adapters:

            # Run warmup repetitions first if configured - as often as configured per model but not times per scenario!
            warmup_repetitions = (
                args.warmup_repetitions
                if args.warmup_repetitions is not None
                else config.get("warmup_repetitions", 0)
            )
            
            if warmup_repetitions > 0:
                print(f"Performing {warmup_repetitions} warm-up repetitions for model {model['name']}...", flush=True)

                for repetition in range(1, warmup_repetitions + 1):
                    print(f"Warm-up repetition {repetition} for model {model['name']}", flush=True)
                    # Match real run payload shape for adapters expecting strict structured output.
                    messages = list(warmup_messages)
                    start_timestamp, start = utc_now(), time.perf_counter()
                    try:
                        response = adapter.generate(list(messages))
                    except KeyboardInterrupt:
                        response = Response(error="Interrupted by user", interrupted=True)
                    except Exception as exc:
                        response = Response(error=f"{type(exc).__name__}: adapter failed")
                    latency = time.perf_counter() - start
                    # IMPORTANT: Mark warm-up runs as such
                    row = {"record_type": "turn", "schema_version": 1, "run_id": run_id,
                        "model": model["name"], "backend": model["type"], "model_id": model.get("model"),
                        "mock": model["type"] == "mock", "scenario": "warmup", "title": "Warm-up",
                        "repetition": repetition, "turn": 1, "expected_turns": 1, #once per warm-up, not per scenario
                        "patient_response_type": "complete", "messages": list(messages),
                        "criteria": {},
                        "started_at": start_timestamp, "ended_at": utc_now(), "latency_s": latency,
                        "ttft_s": response.ttft_s, "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens, "token_source": response.token_source,
                        "tokens_per_s": response.output_tokens / latency if response.output_tokens is not None and latency > 0 else None,
                        "response": response.text, "error": response.error,
                        "status": "interrupted" if response.interrupted else "error" if response.error else "ok",
                        "finish_reason": response.finish_reason,
                        "warmup": True}
                    append_record(output, row)
                    if response.interrupted:
                        raise KeyboardInterrupt
                    if response.error:
                        print(f"Warning: Repetition {repetition} failed for model {model['name']} in warm-up repetition {repetition}: {response.error}")

                    messages.append({"role": "assistant", "content": response.text})

            #Now perform the actual benchmark runs for current model for each scenario 
            for scenario in scenarios:
                for repetition in range(1, repetitions + 1):
                    messages = [{"role": "system", "content": scenario.system_prompt}] + list(scenario.context)
                    for turn_number, turn in enumerate(scenario.patient_turns, 1):
                        messages.append({"role": "user", "content": turn["message"]})
                        start_timestamp, start = utc_now(), time.perf_counter()
                        try:
                            response = adapter.generate(list(messages))
                        except KeyboardInterrupt:
                            response = Response(error="Interrupted by user", interrupted=True)
                        except Exception as exc:
                            response = Response(error=f"{type(exc).__name__}: adapter failed")
                        latency = time.perf_counter() - start
                        row = {"record_type": "turn", "schema_version": 1, "run_id": run_id,
                               "model": model["name"], "backend": model["type"], "model_id": model.get("model"),
                               "mock": model["type"] == "mock", "scenario": scenario.id, "title": scenario.title,
                               "repetition": repetition, "turn": turn_number, "expected_turns": len(scenario.patient_turns),
                               "patient_response_type": turn.get("response_type"), "messages": list(messages),
                               "criteria": {**scenario.criteria, **turn.get("criteria", {})},
                               "started_at": start_timestamp, "ended_at": utc_now(), "latency_s": latency,
                               "ttft_s": response.ttft_s, "input_tokens": response.input_tokens,
                               "output_tokens": response.output_tokens, "token_source": response.token_source,
                               "tokens_per_s": response.output_tokens / latency if response.output_tokens is not None and latency > 0 else None,
                               "response": response.text, "error": response.error,
                               "status": "interrupted" if response.interrupted else "error" if response.error else "ok",
                               "finish_reason": response.finish_reason}
                        append_record(output, row)
                        if response.interrupted:
                            raise KeyboardInterrupt
                        if response.error:
                            break
                        messages.append({"role": "assistant", "content": response.text})
    except KeyboardInterrupt:
        status = "interrupted"
    except Exception:
        status = "failed"
        raise
    finally:
        append_record(output, {"record_type": "run_end", "run_id": run_id,
                               "ended_at": utc_now(), "status": status})
    return 130 if status == "interrupted" else 0