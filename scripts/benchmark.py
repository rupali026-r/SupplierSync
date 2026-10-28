"""Generate and process a repeatable large batch; prints measured performance."""

import argparse
import json
import tempfile
import time
from pathlib import Path

from suppliersync.generate import generate
from suppliersync.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=100_000)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="suppliersync-bench-") as temp:
        root = Path(temp)
        inputs = root / "data" / "input"
        db = root / "data" / "bench.db"
        expected = generate(inputs, args.records)
        start = time.perf_counter()
        report = run_pipeline(inputs, db)
        elapsed = time.perf_counter() - start
        print(
            json.dumps(
                {
                    "requested_records": args.records,
                    "generated": expected,
                    "elapsed_seconds": round(elapsed, 3),
                    "throughput_records_per_second": round(
                        report["input_count"] / elapsed, 1
                    )
                    if elapsed
                    else None,
                    "result": report,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
