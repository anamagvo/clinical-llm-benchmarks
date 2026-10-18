"""Unit tests only: no inference, no runner calls, not even a mock benchmark."""
import json
from pathlib import Path
import pytest
import yaml
from benchmark.run import DEFAULT_REPETITIONS, positive_repetitions
from benchmark.scenarios import load_scenarios
from benchmark.evaluation import evaluate_turn
from benchmark.metrics import distribution
from benchmark.report import summarize
from benchmark.storage import append_record, read_records

ROOT = Path(__file__).resolve().parents[1]


def test_default_repetitions():
    assert DEFAULT_REPETITIONS == 1000
    assert yaml.safe_load((ROOT / "config.yaml").read_text())["repetitions"] == 1000


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_repetitions(value):
    with pytest.raises(ValueError):
        positive_repetitions(value)


def test_scenario_response_types():
    for scenario in load_scenarios(ROOT / "scenarios"):
        assert {t["response_type"] for t in scenario.patient_turns} == {"complete", "incomplete", "ambiguous"}


def test_follow_up_must_be_question():
    record = {"status": "ok", "criteria": {"follow_up": [["seit wann"]]}, "response": "Seit wann ist unbekannt."}
    assert evaluate_turn(record)["checks"]["follow_up_1"] is False
    record["response"] = "Seit wann bestehen die Schmerzen?"
    assert evaluate_turn(record)["checks"]["follow_up_1"] is True


def test_extraction_matches_and_unknown_is_not_invented():
    record = {"status": "ok", "criteria": {"expected_extraction": {"severity": 7, "allergies": None}},
              "response": json.dumps({"reply": "Danke.", "extracted": {"severity": 7, "allergies": None}})}
    assert evaluate_turn(record)["score"] == 1
    record["response"] = json.dumps({"reply": "Danke.", "extracted": {"severity": 3, "allergies": "keine"}})
    assert evaluate_turn(record)["score"] == 0


def test_escalation_same_turn():
    record = {"status": "ok", "criteria": {"escalation_required": True}, "response": "Bitte rufen Sie 112."}
    assert evaluate_turn(record)["checks"]["escalation"] is True
    record["response"] = "Bitte warten Sie."
    assert evaluate_turn(record)["checks"]["escalation"] is False


def test_safety_rejects_forbidden_phrase():
    record = {"status": "ok", "criteria": {"forbidden": ["nehmen sie"]}, "response": "Nehmen Sie 500 mg."}
    assert evaluate_turn(record)["checks"]["safety"] is False


def test_quantiles():
    assert distribution([1, 2, 3, 4, 5]) == {"n": 5, "median": 3, "p95": 4.8, "p99": 4.96}
    assert distribution([None])["median"] is None


def test_partial_jsonl(tmp_path):
    path = tmp_path / "raw.jsonl"
    append_record(path, {"response": "actual recorded text"})
    with path.open("a") as file:
        file.write('{"response":')
    with pytest.warns(UserWarning):
        assert list(read_records(path)) == [{"response": "actual recorded text"}]


def test_failure_counts_and_mock_separation():
    base = {"run_id": "fixture", "model": "same", "scenario": "s", "repetition": 1,
            "expected_turns": 1, "turn": 1, "mock": False, "status": "ok", "latency_s": 1,
            "output_tokens": 10, "tokens_per_s": 10}
    rows = [base, {**base, "repetition": 2, "status": "error", "latency_s": 999},
            {**base, "mock": True, "latency_s": .01}]
    real, mock = summarize(rows)
    assert real["failed_turns"] == 1
    assert real["latency_s_median"] == 1
    assert real["incomplete_repetitions"] == 1
    assert mock["mock"] is True
    assert mock["latency_s_median"] == .01
