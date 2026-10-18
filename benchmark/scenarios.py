from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class Scenario:
    id: str
    title: str
    system_prompt: str
    patient_turns: list[dict]
    criteria: dict = field(default_factory=dict)
    context: list[dict] = field(default_factory=list)


def load_scenarios(directory: str | Path) -> list[Scenario]:
    scenarios = []
    for path in sorted(Path(directory).glob("*.y*ml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path.name}: expected a mapping")
        for key in ("id", "title", "system_prompt", "patient_turns"):
            if key not in data:
                raise ValueError(f"{path.name}: missing field '{key}'")
        turns = data["patient_turns"]
        if not isinstance(turns, list) or not turns:
            raise ValueError(f"{path.name}: patient_turns must be a nonempty list")
        turns = [{"message": t, "criteria": {}} if isinstance(t, str) else t for t in turns]
        if any(not isinstance(t, dict) or not isinstance(t.get("message"), str) for t in turns):
            raise ValueError(f"{path.name}: every turn needs a message")
        context = data.get("context", [])
        if not isinstance(context, list) or any(not isinstance(m, dict) or m.get("role") not in
                ("user", "assistant") or not isinstance(m.get("content"), str) for m in context):
            raise ValueError(f"{path.name}: invalid context messages")
        scenarios.append(Scenario(
            id=data["id"], title=data["title"],
            system_prompt=data["system_prompt"].strip(),
            patient_turns=turns,
            criteria=data.get("criteria", {}) or {},
            context=context,
        ))
    if not scenarios:
        raise ValueError(f"No scenarios found in {directory}")
    return scenarios
