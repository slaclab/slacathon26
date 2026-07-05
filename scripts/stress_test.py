#!/usr/bin/env python3
"""
Stress test for 500 concurrent users using Xopt optimization + leaderboard submissions.

Usage:
    # 1. Make sure the server is running (or will be)
    # 2. python scripts/stress_test.py --users 500 --iterations 15 --base-url http://127.0.0.1:8888/slacathon26

This script will:
- Generate 500 test API keys (stress_user_0000 ... stress_user_0499)
- Insert them into the database (so the server accepts them after restart)
- Launch N threads (default 500), each running an independent Xopt optimization
- Each thread submits its best result to the leaderboard

Requirements:
    pip install xopt requests numpy
    The server should have a high enough MAX_VALIDATIONS_PER_USER (e.g. 10000)
"""

import argparse
import concurrent.futures
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Make both the package and clients importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from slacathon.db import init_db, upsert_user
from clients.xopt_optimizer import XoptOptimizer


def generate_test_keys(n: int) -> List[str]:
    """Generate n test API keys."""
    return [f"stress_user_{i:04d}" for i in range(n)]


def prepare_test_users(keys: List[str]) -> None:
    """Insert test users into the database so the server will accept the keys."""
    init_db()
    print(f"Preparing {len(keys)} test users in the database...")
    for i, key in enumerate(keys):
        upsert_user(key, f"StressUser{i:04d}")
    print("Test users inserted. IMPORTANT: Restart the server now if it is already running,")
    print("so it picks up the new keys from the database.\n")


def run_single_user_stress(
    user_index: int,
    api_key: str,
    base_url: str,
    n_iterations: int,
    n_initial: int = 5,
    target_score: float = 1e-2,
) -> Dict[str, Any]:
    """
    One thread's work: run Xopt optimization + submit best result.
    """
    thread_name = f"User-{user_index:04d}"
    start_time = time.time()

    try:
        # Small random delay so not all threads hammer the server at the exact same microsecond
        time.sleep(random.uniform(0.0, 1.5))

        opt = XoptOptimizer(api_key=api_key, base_url=base_url)

        # Run optimization
        best_x, best_score, result = opt.optimize(
            n_iterations=n_iterations,
            n_initial=n_initial,
            target_score=target_score,
        )

        submitted = False
        rank = None
        leaderboard_size = None

        if best_x is not None:
            # Submit the best found point
            submit_resp = opt.submit_to_leaderboard(best_x)
            if submit_resp:
                submitted = submit_resp.get("submitted", False)
                rank = submit_resp.get("rank")
                leaderboard_size = submit_resp.get("leaderboard_size")

        duration = time.time() - start_time

        return {
            "user_index": user_index,
            "api_key": api_key,
            "success": True,
            "final_score": float(best_score) if best_score is not None else None,
            "submitted": submitted,
            "rank": rank,
            "leaderboard_size": leaderboard_size,
            "duration_sec": round(duration, 2),
            "iterations": n_iterations,
        }

    except Exception as e:
        duration = time.time() - start_time
        return {
            "user_index": user_index,
            "api_key": api_key,
            "success": False,
            "error": str(e),
            "duration_sec": round(duration, 2),
        }


def main():
    parser = argparse.ArgumentParser(description="Stress test 500 users with Xopt + submissions")
    parser.add_argument("--users", type=int, default=500, help="Number of concurrent users/threads")
    parser.add_argument("--iterations", type=int, default=15, help="Xopt iterations per user")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8888/slacathon26",
        help="Base URL of the running server (include /slacathon26 if using root_path)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=500,
        help="Maximum concurrent threads (use lower value if your machine can't handle 500)",
    )
    parser.add_argument(
        "--prepare-keys",
        action="store_true",
        default=True,
        help="Insert the 500 test keys into the database before starting",
    )
    parser.add_argument(
        "--no-prepare-keys",
        dest="prepare_keys",
        action="store_false",
        help="Skip inserting test keys (assume they already exist)",
    )
    parser.add_argument(
        "--target-score",
        type=float,
        default=1e-2,
        help="Target score to stop early (per user)",
    )

    args = parser.parse_args()

    N = args.users
    keys = generate_test_keys(N)

    if args.prepare_keys:
        prepare_test_users(keys)
        print("Sleeping 3 seconds so you have time to restart the server if needed...")
        time.sleep(3)

    print(f"Starting stress test with {N} users, {args.iterations} iterations each...")
    print(f"Base URL: {args.base_url}")
    print(f"Max concurrent workers: {args.max_workers}")
    print("-" * 60)

    start_all = time.time()
    results: List[Dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_user = {
            executor.submit(
                run_single_user_stress,
                i,
                key,
                args.base_url,
                args.iterations,
                5,
                args.target_score,
            ): i
            for i, key in enumerate(keys)
        }

        for future in concurrent.futures.as_completed(future_to_user):
            res = future.result()
            results.append(res)

            # Live progress
            if res["success"]:
                print(
                    f"[{res['user_index']:04d}] score={res.get('final_score'):.6f} "
                    f"submitted={res.get('submitted')} rank={res.get('rank')} "
                    f"({res['duration_sec']:.1f}s)"
                )
            else:
                print(f"[{res['user_index']:04d}] ERROR: {res.get('error')}")

    total_time = time.time() - start_all

    # Summary
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    submitted = [r for r in successes if r.get("submitted")]
    ranks = [r["rank"] for r in submitted if r.get("rank") is not None]

    print("\n" + "=" * 60)
    print("STRESS TEST SUMMARY")
    print("=" * 60)
    print(f"Total users attempted:     {len(results)}")
    print(f"Successful runs:           {len(successes)}")
    print(f"Failed runs:               {len(failures)}")
    print(f"Successful submissions:    {len(submitted)}")
    if ranks:
        print(f"Best rank achieved:        {min(ranks)}")
        print(f"Worst rank achieved:       {max(ranks)}")
    print(f"Total wall time:           {total_time:.1f} seconds")
    if successes:
        avg_duration = sum(r["duration_sec"] for r in successes) / len(successes)
        print(f"Average time per user:     {avg_duration:.1f} seconds")

    # Optional: save results
    import json
    out_file = Path("stress_results.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results written to {out_file}")


if __name__ == "__main__":
    main()