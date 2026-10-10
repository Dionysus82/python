"""Execute the RAG evaluation suite against the local database."""

from __future__ import annotations

import json

from app.database import get_session_factory
from app.evaluation.runner import run_evaluation


def main() -> None:
    session = get_session_factory()()
    try:
        summary = run_evaluation(session)
    finally:
        session.close()
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, indent=2))
    print("--- cases ---")
    for item in summary["results"]:
        mark = "PASS" if item["passed"] else "FAIL"
        print(f"{mark} {item['id']} {item['checks']}")


if __name__ == "__main__":
    main()
