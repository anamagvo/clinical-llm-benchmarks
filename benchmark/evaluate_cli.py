import argparse
from pathlib import Path
import yaml
from .evaluation import evaluate_turn
from .storage import append_record, read_records


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate saved responses without rerunning benchmark models")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--judge-config", help="Optional YAML with a judge model entry; triggers model calls")
    args = parser.parse_args(argv)
    source, target = Path(args.input), Path(args.output)
    if source.resolve() == target.resolve():
        raise ValueError("Evaluation output must differ from raw input")
    judge = None
    if args.judge_config:
        judge = yaml.safe_load(Path(args.judge_config).read_text(encoding="utf-8"))["judge"]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8"):
        pass
    for record in read_records(source):
        if record.get("record_type") == "turn":
            record["evaluation"] = evaluate_turn(record)
            if judge:
                from .judge import evaluate_with_judge
                record["judge_evaluation"] = evaluate_with_judge(record, judge)
        append_record(target, record)
    return 0