"""
Two required demo requests against the running API.

Start the server first:
    uvicorn main:app --reload --port 8000

Then run:
    python test_client.py
"""
import json
import requests

BASE = "http://127.0.0.1:8000"

STANDARD_REQUEST = (
    "Create a project plan for migrating our internal customer support "
    "tool from a legacy on-premise system to a cloud-based helpdesk platform. "
    "The project should take about 3 months and involve engineering, support, and IT teams."
)

# Deliberately ambiguous / multi-step / under-specified / conflicting:
# - no company name, no budget, no real attendees
# - asks for two different deliverables ("plan" AND "decide if we even need it")
# - contradictory ask: "quick and lightweight" but also "extremely detailed"
COMPLEX_REQUEST = (
    "We might need to replace our vendor for background checks, or maybe just "
    "renegotiate, not sure yet -- can you put together something for leadership "
    "that's quick and lightweight but also extremely detailed, covering cost, "
    "risk, and a recommendation, and also basically function as meeting notes "
    "for a decision that hasn't happened yet."
)


def run(label: str, request_text: str):
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    print(f"Request: {request_text}\n")
    resp = requests.post(f"{BASE}/agent", json={"request": request_text}, timeout=120)
    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text)
        return
    data = resp.json()
    print(f"Document type : {data['document_type']}")
    print(f"Message       : {data['message']}")
    print(f"Assumptions   :")
    for a in data["assumptions"]:
        print(f"  - {a}")
    print(f"Self-generated task list:")
    for t in data["task_list"]:
        print(f"  [{t['status']:>11}] #{t['id']} {t['title']}")
    print(f"Reflection    : {data['reflection_summary']}")
    print(f"Docx saved to : {data['file_path']}")


if __name__ == "__main__":
    run("TEST 1 - STANDARD BUSINESS REQUEST (Project Plan)", STANDARD_REQUEST)
    run("TEST 2 - COMPLEX / AMBIGUOUS / CONFLICTING REQUEST", COMPLEX_REQUEST)
