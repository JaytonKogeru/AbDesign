"""Submit a sample job to the local API and poll until completion.

Usage::

    python scripts/smoke_test.py --base-url http://localhost:8000

The script expects the API server to be running (``uvicorn api.main:app``)
*and* a worker process consuming the queue (``python -m worker.worker``).
Optional ``--api-key`` can be provided if API key auth is enabled.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = PROJECT_ROOT / "samples"
DEFAULT_BASE_URL = "http://localhost:8000"


def submit_job(base_url: str, api_key: str | None = None) -> Dict[str, str]:
    """Submit a sample VHH/target pair and return task metadata."""

    vhh_path = SAMPLES_DIR / "vhh_sample.pdb"
    target_path = SAMPLES_DIR / "target_sample.pdb"

    files = {
        "vhh_file": (vhh_path.name, vhh_path.read_bytes(), "chemical/x-pdb"),
        "target_file": (target_path.name, target_path.read_bytes(), "chemical/x-pdb"),
    }
    data = {"mode": "separate"}
    headers = {"X-API-Key": api_key} if api_key else {}

    response = requests.post(f"{base_url}/submit", files=files, data=data, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def poll_result(base_url: str, task_id: str, *, retries: int = 10, delay: float = 2.0) -> Dict[str, object]:
    """Poll the result endpoint until the task finishes or retries are exhausted."""

    for attempt in range(1, retries + 1):
        response = requests.get(f"{base_url}/result/{task_id}", timeout=15)
        response.raise_for_status()
        payload = response.json()

        status = payload.get("status")
        print(f"[poll {attempt}/{retries}] task={task_id} status={status}")

        if status not in {"queued", "started"}:
            return payload
        time.sleep(delay)

    raise RuntimeError(f"Task {task_id} did not finish after {retries} attempts")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a smoke test against the local API")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL for the running API")
    parser.add_argument("--api-key", default=None, help="API key header if your server enforces it")
    args = parser.parse_args()

    print(f"Submitting sample job to {args.base_url}...")
    submission = submit_job(args.base_url, api_key=args.api_key)
    task_id = submission["task_id"]
    print(f"Task accepted: task_id={task_id}, job_id={submission.get('job_id')}")

    result = poll_result(args.base_url, task_id)
    print("\nFinal result:")
    print(json.dumps(result, indent=2))

    if result.get("status") != "succeeded":
        raise SystemExit("Smoke test failed: task did not succeed")

    artifacts = result.get("result_metadata", {})
    print("\nArtifacts produced:")
    for label, path in artifacts.items():
        print(f"  - {label}: {path}")


if __name__ == "__main__":
    main()
