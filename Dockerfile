FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /uvx /bin/
WORKDIR /app
COPY . .
RUN uv sync --locked --no-dev
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "run_benchmark.py"]
CMD ["--config", "config.yaml"]
