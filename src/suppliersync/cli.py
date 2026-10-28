"""Command line interface."""
import argparse
import json
import logging
import sqlite3
from pathlib import Path

from .generate import generate
from .pipeline import connect, export_products, run_pipeline


def main() -> None:
    p = argparse.ArgumentParser(prog="suppliersync")
    sub = p.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="generate deterministic sample feeds")
    gen.add_argument("--output", default="data/input"); gen.add_argument("--records", type=int, default=40); gen.add_argument("--seed", type=int, default=1729)
    run = sub.add_parser("run", help="validate and publish input feeds")
    run.add_argument("--input", default="data/input"); run.add_argument("--db", default="data/suppliersync.db"); run.add_argument("--report", default="reports/latest.json")
    export = sub.add_parser("export", help="export canonical products as CSV")
    export.add_argument("--db", default="data/suppliersync.db"); export.add_argument("--output", default="outputs/products.csv")
    report = sub.add_parser("report", help="print run reconciliation from the database")
    report.add_argument("--db", default="data/suppliersync.db")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "generate":
        if args.records < 0: p.error("--records must be non-negative")
        print(json.dumps(generate(args.output, args.records, args.seed), indent=2))
    elif args.command == "run":
        result = run_pipeline(args.input, args.db, args.report)
        print(json.dumps(result, indent=2))
        if result["status"] != "succeeded": raise SystemExit(1)
    elif args.command == "export":
        export_products(args.db, args.output); print(args.output)
    else:
        with connect(args.db) as db:
            print(json.dumps([dict(r) for r in db.execute("SELECT * FROM pipeline_runs ORDER BY started_at")], indent=2))


if __name__ == "__main__":
    main()
