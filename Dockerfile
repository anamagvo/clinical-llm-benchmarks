FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /uvx /bin/
WORKDIR /app
COPY . .
RUN uv sync --locked --no-dev
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "run_benchmark.py", "--config", "config.yaml"]
CMD ["bash", "-c", "sleep 1 && python -c \"from benchmark.report import write_reports; from benchmark.storage import read_records; import glob, os; files = glob.glob('results/raw-*.jsonl'); [write_reports(list(read_records(f)), 'results/report') for f in files if f]\""]
