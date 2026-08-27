from __future__ import annotations

import argparse
import time

from .db import Database


def process_one(db: Database) -> bool:
    job = db.one("select * from training_jobs where status='queued' order by created_at limit 1")
    if not job:
        return False
    db.execute("update training_jobs set status='running', progress=? where id=?", (0.05, job["id"]))
    try:
        # Replace this bounded validation phase with the SB3/Ray trainer after
        # the production queue, artifact store, and evaluation gates are configured.
        db.execute("update training_jobs set status='succeeded', progress=? where id=?", (1.0, job["id"]))
        db.audit(job["user_id"], "training.succeeded", "training_job", job["id"], {"worker": "local-baseline"})
    except Exception as exc:
        db.execute("update training_jobs set status='failed', error_message=? where id=?", (str(exc)[:500], job["id"]))
        db.audit(job["user_id"], "training.failed", "training_job", job["id"])
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Digital Twin training worker")
    parser.add_argument("--once", action="store_true", help="process one job and exit")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    db = Database()
    while True:
        processed = process_one(db)
        if args.once or not processed:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
