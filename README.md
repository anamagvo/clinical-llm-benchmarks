# clinical-llm-benchmark

Portable Python scripts for external AI workstations. Records actual model replies
to German clinical patient-intake dialogues, evaluates saved replies, and produces
static HTML/CSV reports. No web application or dashboard.

> Research only. Not a medical device. Use synthetic patients, never real patient
> data. Keyword checks and optional model judges are not clinical validation.
> This implementation has not been benchmarked here. Unit tests are not evidence
> of real model quality or speed. Docker and real inference must be verified on
> the target workstation.

## Run on the workstation (Python 3.11+ and uv)

Run all commands from `clinical-llm-benchmark/`. Configure the model ID and server
address in `config.yaml`. Start an Ollama server separately, then download the
configured example model with `ollama pull llama3.1:8b`.

```bash
uv sync --locked
uv run run_benchmark.py --config config.yaml --output results/raw.jsonl
uv run evaluate_results.py --input results/raw.jsonl --output results/evaluated.jsonl
uv run generate_report.py --input results/evaluated.jsonl --output results/report
```

Default: **1,000 repetitions per model and scenario** (3 scenarios × 3 turns =
9,000 requests per model when no errors occur). Each repetition starts a fresh
conversation; turns retain the system prompt, scenario context and actual prior
assistant replies. Execution is sequential, without retries or warm-up exclusions.
Override with `--repetitions 10` or change `repetitions` in YAML.
Each run/evaluation requires a new output filename; existing files are refused.
Installed entry commands `benchmark`, `evaluate-results`, `generate-report` also
work with `uv run`. The benchmark command **only records**, never auto-evaluates.

Outputs: `raw.jsonl` (authoritative responses/measurements), `evaluated.jsonl`
(same records with scoring), `report/turns.csv`, `report/summary.csv`,
`report/report.html`. Open the HTML file directly in a browser. Reports can also
read raw files; quality fields are then N/A. No model calls occur during reporting
or default deterministic evaluation.

### Optional synthetic pipeline check (on the workstation only)

```bash
uv run run_benchmark.py --mock --repetitions 1 --output results/mock-raw.jsonl
uv run evaluate_results.py --input results/mock-raw.jsonl --output results/mock-evaluated.jsonl
uv run generate_report.py --input results/mock-evaluated.jsonl --output results/mock-report
```

**MOCK DATA IS SYNTHETIC**, with canned replies and word-count token estimates.
Never cite mock output as real LLM performance or quality. Every mock turn is
marked; report groups never combine mock and real measurements. Mock judge
results are also explicitly marked and kept separate.

## Docker

The image installs locked uv dependencies; the benchmark container needs CPU
only because inference happens in a separate server.

For an existing server on the host, set `base_url` to
`http://host.docker.internal:11434` (Ollama), or
`http://host.docker.internal:8000/v1` (OpenAI-compatible).
The host server must listen on an interface accessible from Docker; restrict
firewall access rather than exposing an unauthenticated inference server publicly.

> Docker troubleshooting note: in the Compose setup, the benchmark container reads
> `/app/config.yaml`, which is mounted from `config_with_docker.yaml` in the repo.
> The model endpoint must therefore be `http://ollama:11434`, not a frontend URL or
> `localhost`. If a model is installed in Ollama but inference still returns 500s,
> check whether the model actually runs in the Ollama container itself, e.g.
> `docker compose exec ollama ollama run qwen3:4b "Hallo"`. A 500 here usually means
> the model cannot be loaded because the VM/container has insufficient RAM or shared
> memory. On Colima this often requires a larger VM, e.g.
> `colima start --cpu 4 --memory 12 --disk 80`.

Alternatively use the optional Ollama service (NVIDIA GPU + container toolkit):

```bash
docker compose --profile gpu up -d ollama
docker compose exec ollama ollama pull llama3.1:8b
```

For that service set `base_url: http://ollama:11434` in `config.yaml`.
Then run:

```bash
docker compose build benchmark
docker compose run --rm benchmark run_benchmark.py --config config.yaml --output results/raw.jsonl
docker compose run --rm benchmark evaluate_results.py --input results/raw.jsonl --output results/evaluated.jsonl
docker compose run --rm benchmark generate_report.py --input results/evaluated.jsonl --output results/report
```

The three mounted paths are `results/`, `scenarios/`, `config.yaml`; outputs remain
on the host. For Docker mock mode use `run_benchmark.py --mock --repetitions 1
--output results/mock-raw.jsonl` after the service name.

## Model adapters and configuration

`model_adapters/base.py` defines `generate(messages) -> Response`.
Backend-specific implementations are separate:

| Type | Interface | Options |
|---|---|---|
| `ollama` | streamed `/api/chat` | `model`, `base_url`, `options`, optional `format` |
| `openai_compat` | streamed `/v1/chat/completions` (vLLM, llama.cpp, LM Studio) | `model`, `base_url`, `temperature`, `request_options`, optional `api_key_env` |
| `mock` | synthetic canned replies | no server |

Both real adapters accept `timeout: [10, 300]` (connect and idle-read seconds).
OpenAI-compatible servers must support SSE and `stream_options.include_usage`;
unsupported request options cause a recorded failure, not silent fallback.
An absent provider token count is **null**, never a word-count estimate.
Configure structured JSON mode with `format: json` for Ollama or
`request_options.response_format` where the OpenAI server supports it.
For authenticated servers set the named environment variable, e.g.
`export MODEL_API_KEY=...`; never write private keys into YAML. Compose forwards
`MODEL_API_KEY`. Add a new adapter subclass and register it in
`model_adapters/__init__.py`.

## Scenarios and deterministic criteria

Three reusable YAML scenarios include conversation context and complete,
incomplete, and ambiguous patient messages. System prompts request JSON:
`{"reply": "German answer with questions", "extracted": {"severity": 7, ...}}`.
Extraction fields are cumulative; unknown information must be `null`.

```yaml
id: example
title: Beispiel
system_prompt: 'Antworte als JSON mit reply und extracted.'
context:
  - role: assistant
    content: "Welche Beschwerden haben Sie?"
criteria:
  require_json: true
  forbidden: ["nehmen sie"]
patient_turns:
  - message: "Ich habe Schmerzen, weiß aber nicht seit wann."
    response_type: ambiguous
    criteria:
      follow_up: [["seit wann", "begonnen"], ["wo", "stelle"]]
      expected_extraction: {onset: null}
```

Global criteria are shallow-merged with per-turn criteria. Each `follow_up` group
needs at least one alternative in a question sentence ending in `?` on that
specific turn. `expected_extraction` checks normalized field values: strings are
case-insensitive and whitespace-normalized, a list allows alternative values,
and `null` requires an explicit unknown value. `escalation_required: true` checks
an escalation phrase on that turn, never a later answer. `forbidden` checks word-
bounded phrases. The score is the unweighted fraction of explicit checks passed;
failed/interrupted turns fail their checks. Missing JSON fails extraction checks.
No language detector, diagnosis engine, semantic equivalence or negation analysis
is claimed. Read the actual transcripts; these heuristic criteria can produce
false positives/negatives, especially escalations containing negation.

### Optional judge-model evaluation

Separate from deterministic evaluation; **this makes extra inference calls**.
Create `judge.yaml` with:

```yaml
judge:
  name: local-judge
  type: ollama
  model: llama3.1:8b
  base_url: http://localhost:11434
  format: json
  options: {temperature: 0}
```

```bash
uv run evaluate_results.py --input results/raw.jsonl --output results/judged.jsonl --judge-config judge.yaml
uv run generate_report.py --input results/judged.jsonl --output results/judged-report
```

Judge responses, errors and scores are recorded in `judge_evaluation` and exposed
separately in turn CSV/HTML, never blended into deterministic quality scores.
Model judges may be biased or follow malicious transcript instructions despite
the judge prompt; do not use them as clinical ground truth.

## Measurements and interruption

Every turn stores UTC start/end timestamps; monotonic wall-clock latency covering
the adapter call; TTFT from HTTP request start to first nonempty text content;
provider input/output token counts; output tokens / full turn latency; exact
response text, input conversation, finish reason, status and sanitized error.
TTFT is a client-observed first-content delay, not a hardware-level token timestamp.
Throughput includes request overhead, unlike decode-only throughput. Unknown counts
remain null. A provider `length` finish reason is recorded for inspection.
Concurrent load, network, model loading and prefix caching affect measurements;
record workstation hardware, server version, model/quantization and load separately.

Reports group by run, model, scenario and mock flag. Successful turns supply median,
P95 and P99 for latency, TTFT, token counts and tokens/s; each metric includes its
sample count. Quantiles interpolate at `(n - 1) * p` (R type 7), including small
samples; empty samples yield N/A. Complete dialogues additionally have total
latency and aggregate output-tokens/latency quantiles across repetitions.
Failed turns are excluded from speed distributions, counted with an attempted-turn
failure rate, and retained in quality checks. Planned, attempted, complete and
incomplete repetitions expose interrupted or unattempted work, not fake samples.

Each JSONL record is appended, flushed and fsynced before the next turn. Ctrl+C
saves accumulated streaming text when available and exits with code 130. Hard
termination preserves already written records, but can lose the current in-flight
turn. Readers warn and ignore a truncated last JSON line only; corruption elsewhere
raises an error. Generate reports/evaluations from partial files using the same
commands. A model error skips remaining turns of that repetition and continues
with the next repetition. No automatic resume or retry: use a new file for a new
run. Don't evaluate a file while it is still being written.

Raw JSONL preserves model text exactly. HTML escapes untrusted text; CSV prefixes
formula-like text with an apostrophe to prevent spreadsheet formula execution.

## Tests (no benchmark execution)

```bash
uv run pytest tests -q
```

Tests use fixed data and simulated stream chunks for rules, quantiles, persistence
and parsing; they never run the benchmark or connect to an inference server.
