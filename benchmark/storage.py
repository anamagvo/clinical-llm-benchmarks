import json
import os
from pathlib import Path


def append_record(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        file.flush()
        os.fsync(file.fileno())


def read_records(path):
    """Ignore only a malformed final line left by a killed writer."""
    import warnings
    with Path(path).open("r", encoding="utf-8") as file:
        line = file.readline()
        number = 0
        while line:
            number += 1
            following = file.readline()
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                if following or line.endswith("\n"):
                    raise ValueError(f"Invalid JSON at line {number}") from None
                warnings.warn(f"Ignored truncated final line {number}")
            line = following