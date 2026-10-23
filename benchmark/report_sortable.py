import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from jinja2 import Template
from .metrics import distribution
from .storage import read_records

METRICS = ["latency_s", "ttft_s", "input_tokens", "output_tokens", "tokens_per_s"]
TURN_FIELDS = ["run_id", "model", "scenario", "repetition", "turn", "mock", "status", "started_at",
               "ended_at", *METRICS, "token_source", "finish_reason", "quality_score", "judge_score",
               "judge_mock", "judge_error", "checks", "response", "error"]
def summarize(turns, records=()):
    groups = defaultdict(list)
    planned = {}
    ended = {}
    for record in records:
        if record.get("record_type") == "run_end":
            ended[record["run_id"]] = record["status"]
        if record.get("record_type") == "run":
            for model in record["models"]:
                for scenario in record["scenario_ids"]:
                    key = (record["run_id"], model["name"], scenario, model["mock"])
                    planned[key] = record["repetitions"]
                    groups[key] = []
    for row in turns:
        # Skip warm-up runs for summary (as they distort the results)
        if row.get("warmup"):
            continue
        groups[(row["run_id"], row["model"], row["scenario"], row["mock"])].append(row)
    summary = []
    for (run_id, model, scenario, mock), rows in groups.items():
        key = (run_id, model, scenario, mock)
        successful = [r for r in rows if r["status"] == "ok"]
        reps = defaultdict(list)
        for row in rows:
            reps[row["repetition"]].append(row)
        complete = [rs for rs in reps.values() if len(rs) == rs[0]["expected_turns"]
                    and all(r["status"] == "ok" for r in rs)]
        count = planned.get(key, len(reps))
        scores = [r.get("evaluation", {}).get("score") for r in rows]
        scores = [s for s in scores if s is not None]
        item = {"run_id": run_id, "model": model, "scenario": scenario, "mock": mock,
                "run_status": ended.get(run_id, "partial_no_end_marker"),
                "planned_repetitions": count, "attempted_repetitions": len(reps),
                "complete_repetitions": len(complete), "incomplete_repetitions": count - len(complete),
                "recorded_turns": len(rows), "successful_turns": len(successful),
                "failed_turns": len(rows) - len(successful),
                "failure_rate": (len(rows) - len(successful)) / len(rows) if rows else None,
                "quality_n": len(scores), "quality_mean": sum(scores) / len(scores) if scores else None}
        for metric in METRICS:
            values = [r.get(metric) for r in successful]
            item.update({f"{metric}_{k}": v for k, v in distribution(values).items()})
        for metric, values in {
            "dialogue_latency_s": [sum(r["latency_s"] for r in rs) for rs in complete],
            "dialogue_tokens_per_s": [sum(r["output_tokens"] for r in rs) / sum(r["latency_s"] for r in rs)
                                      for rs in complete if all(r.get("output_tokens") is not None for r in rs)
                                      and sum(r["latency_s"] for r in rs) > 0],
        }.items():
            item.update({f"{metric}_{k}": v for k, v in distribution(values).items()})
        summary.append(item)
    return summary


def csv_safe(value):
    # Untrusted model text must not become a spreadsheet formula.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({k: csv_safe(v) for k, v in row.items()} for row in rows)


def write_reports(records, output_dir):
    turns = [r for r in records if r.get("record_type") == "turn"]
    summary = summarize(turns, records)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    flattened = []
    for row in turns:
        evaluation = row.get("evaluation", {})
        judge = row.get("judge_evaluation", {})
        flattened.append({**row, "quality_score": evaluation.get("score"), "judge_score": judge.get("score"),
                          "judge_mock": judge.get("mock"), "judge_error": judge.get("error"),
                          "checks": json.dumps(evaluation.get("checks", {}), ensure_ascii=False)})
    write_csv(out / "turns.csv", TURN_FIELDS, flattened)
    fields = list(summary[0]) if summary else ["model", "scenario"]
    write_csv(out / "summary.csv", fields, summary)
    (out / "report.html").write_text(HTML.render(turns=turns, summary=summary, fields=fields,
                                                has_mock=any(r["mock"] or r.get("judge_evaluation", {}).get("mock") for r in turns)), encoding="utf-8")
    return out / "summary.csv", out / "report.html"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate offline HTML and CSV reports from saved results")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="results/report")
    args = parser.parse_args(argv)
    write_reports(list(read_records(args.input)), args.output)
    return 0
HTML = Template("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Clinical LLM benchmark report</title><style>
body{font-family:system-ui,sans-serif;margin:2rem}table{border-collapse:collapse;margin-bottom:2rem}
th,td{border:1px solid #ccc;padding:.4rem;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}
.sortable { cursor: pointer; }
.sort-arrow { margin-left: 5px; }
</style><script>
function sortTable(n) {
    var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
    table = document.getElementById("summary-table");
    switching = true;
    dir = "asc";
    while (switching) {
        switching = false;
        rows = table.rows;
        for (i = 1; i < (rows.length - 1); i++) {
            shouldSwitch = false;
            x = rows[i].getElementsByTagName("TD")[n];
            y = rows[i + 1].getElementsByTagName("TD")[n];
            if (dir == "asc") {
                if (x.innerHTML.toLowerCase() > y.innerHTML.toLowerCase()) {
                    shouldSwitch = true;
                    break;
                }
            } else if (dir == "desc") {
                if (x.innerHTML.toLowerCase() < y.innerHTML.toLowerCase()) {
                    shouldSwitch = true;
                    break;
                }
            }
        }
        if (shouldSwitch) {
            rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
            switching = true;
            switchcount++;
        } else {
            if (switchcount == 0 && dir == "asc") {
                dir = "desc";
                switching = true;
            }
        }
    }
    // Update arrow indicators
    updateSortIndicators(n, dir);
}

function updateSortIndicators(columnIndex, direction) {
    var table = document.getElementById("summary-table");
    var headers = table.getElementsByTagName("TH");
    for (var i = 0; i < headers.length; i++) {
        var arrow = headers[i].querySelector('.sort-arrow');
        if (i === columnIndex) {
            if (direction === "asc") {
                arrow.innerHTML = " ▲";
            } else {
                arrow.innerHTML = " ▼";
            }
        } else {
            if (arrow) arrow.innerHTML = "";
        }
    }
}
</script></head><body><h1>Clinical LLM benchmark report</h1>
<p>Research only. Not a medical device. Deterministic checks are heuristic, not clinical validation.</p>
{% if has_mock %}<p><strong>MOCK / SYNTHETIC DATA — not real model performance or quality.</strong></p>{% endif %}
<p>Successful-turn distributions: median / P95 / P99, linear interpolation (n−1)p.
Failed and interrupted turns are excluded from speed distributions but counted as failures.
Quality includes recorded failed turns; unattempted turns are shown through incomplete repetitions.</p>
<h2>Per model and scenario</h2>
<table id="summary-table"><tr>{% for key in fields %}<th class="sortable" onclick="sortTable({{ loop.index0 }})">{{key}}<span class="sort-arrow"></span></th>{% endfor %}</tr>
{% for row in summary %}<tr>{% for key in fields %}<td>{{row.get(key) if row.get(key) is not none else 'N/A'}}</td>{% endfor %}</tr>{% endfor %}</table>
<h2>Recorded responses</h2>{% for row in turns %}
<details><summary>{{row.model}} / {{row.scenario}} / repetition {{row.repetition}} / turn {{row.turn}} — {{row.status}}{% if row.mock %} — MOCK{% endif %}</summary>
{% for message in row.messages %}<p><strong>{{message.role}}</strong></p><pre>{{message.content}}</pre>{% endfor %}
<p><strong>Actual response</strong></p><pre>{{row.response}}</pre><p>Error: {{row.error or 'none'}}</p>
<pre>{{row.evaluation}}</pre>{% if row.judge_evaluation %}<p>Optional judge (separate):</p><pre>{{row.judge_evaluation}}</pre>{% endif %}</details>
{% endfor %}</body></html>""", autoescape=True)