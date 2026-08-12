import os
import time

import requests

API_KEY = os.environ["API_KEY"]
BASE_URL = os.getenv("BASE_URL", "https://ad-accel-online-ml-dev.slac.stanford.edu/slacathon26/")

headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

def run_validation(params, poll_interval=2):
    inp = {"q1": params[0], "q2": params[1], "q3": params[2], "d2": params[3], "d3": params[4]}
    r = requests.post(f"{BASE_URL}/validate", headers=headers, json={"input": inp})
    r.raise_for_status()
    job = r.json()
    job_id = job["job_id"]
    print(f"job {job_id}")

    while True:
        j = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=headers).json()
        if j["status"] == "completed":
            return j.get("result")
        time.sleep(poll_interval)

print(run_validation([2.2547133301706257, -2.223405741870012, 0.9588998760031707, 0.033, 1.413]))
print(run_validation([2.5537242710909087, -2.518264797355262, 1.0860652900429026, 0.033, 1.413]))
