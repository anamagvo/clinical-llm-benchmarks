"""Exercise offline scripts with fixed records, without running a benchmark."""
import csv
import json
from benchmark.evaluate_cli import main as evaluate_main
from benchmark.report import main as report_main
from benchmark.storage import append_record, read_records


def test_offline_evaluation_and_reports(tmp_path):
    raw, evaluated = tmp_path / "raw.jsonl", tmp_path / "evaluated.jsonl"
    append_record(raw, {"record_type": "run", "run_id": "fixed", "repetitions": 1000,
                        "models": [{"name": "fixture", "mock": True}], "scenario_ids": ["s"]})
    append_record(raw, {"record_type": "turn", "run_id": "fixed", "model": "fixture",
                        "scenario": "s", "repetition": 1, "turn": 1, "expected_turns": 2,
                        "mock": True, "status": "ok", "latency_s": 2, "output_tokens": 10,
                        "tokens_per_s": 5, "messages": [{"role": "user", "content": "<script>alert(1)</script>"}],
                        "response": json.dumps({"reply": "Seit wann haben Sie Schmerzen?", "extracted": {}}),
                        "criteria": {"follow_up": [["seit wann"]]}, "error": None})
    assert evaluate_main(["--input", str(raw), "--output", str(evaluated)]) == 0
    turns = [r for r in read_records(evaluated) if r["record_type"] == "turn"]
    assert turns[0]["evaluation"]["score"] == 1
    assert report_main(["--input", str(evaluated), "--output", str(tmp_path / "report")]) == 0
    with (tmp_path / "report/summary.csv").open() as file:
        row = next(csv.DictReader(file))
    assert row["planned_repetitions"] == "1000"
    assert row["incomplete_repetitions"] == "1000"
    assert row["quality_mean"] == "1.0"
    assert row["latency_s_p99"] == "2.0"
    assert (tmp_path / "report/turns.csv").exists()


def test_reports_do_not_invoke_models(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline reporting must never connect to a model")
    monkeypatch.setattr("model_adapters.streaming.requests.post", forbidden)
    raw = tmp_path / "empty.jsonl"
    raw.write_text("")
    assert report_main(["--input", str(raw), "--output", str(tmp_path / "report")]) == 0