#!/usr/bin/env python3
"""
Run all 4 MVP test cases and verify results.

This script submits all 4 test cases to the running API server,
waits for completion, and verifies the results.

Usage:
    python tests/integration/run_mvp_tests.py
"""

import json
import time
import sys
import requests

# API base URL
BASE_URL = "http://localhost:8000"

# Test cases from the MVP task list
TEST_CASES = {
    "prohibited": {
        "name": "Deepfake Generator (UNACCEPTABLE)",
        "description": (
            "An AI application that generates realistic nude images of people based on "
            "their regular photos, allowing users to create intimate content without the "
            "subject's knowledge or consent."
        ),
        "expected_risk_level": "unacceptable",
        "expected_requirements_range": (0, 0),  # Should have NO requirements
    },
    "high-risk-healthcare": {
        "name": "Hospital Triage (HIGH)",
        "description": (
            "An AI system for hospital emergency room triage that analyzes patient symptoms, "
            "vital signs, and medical history to prioritize patients and recommend initial "
            "treatment protocols. The system assists medical staff in making time-critical "
            "decisions about patient care priority."
        ),
        "expected_risk_level": "high",
        "expected_requirements_range": (10, 100),  # Should have 10-100 requirements (20 articles x ~3 each)
    },
    "limited-risk": {
        "name": "E-commerce Chatbot (LIMITED)",
        "description": (
            "A customer service chatbot that handles common inquiries about products, "
            "shipping, and returns for an e-commerce store. The chatbot uses natural "
            "language processing to understand customer questions and provide helpful "
            "responses about order status and store policies."
        ),
        "expected_risk_level": "limited",
        "expected_requirements_range": (0, 10),
    },
    "minimal-risk": {
        "name": "Movie Recommender (MINIMAL)",
        "description": (
            "An AI recommendation system that suggests movies to users based on their "
            "viewing history, ratings, and preferences for a streaming platform. The "
            "system personalizes content discovery without making any consequential "
            "decisions about users."
        ),
        "expected_risk_level": "minimal",
        "expected_requirements_range": (0, 5),
    },
}


def submit_job(description: str) -> str:
    """Submit a job and return the job ID."""
    response = requests.post(
        f"{BASE_URL}/api/analyze",
        json={"description": description},
    )
    response.raise_for_status()
    return response.json()["job_id"]


def wait_for_job(job_id: str, timeout: int = 300) -> dict:
    """Wait for a job to complete and return the status.

    Default timeout of 300s to accommodate high-risk systems which generate
    many requirements and take longer to process.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = requests.get(f"{BASE_URL}/api/status/{job_id}")
        response.raise_for_status()
        status = response.json()

        if status["status"] == "completed":
            return status
        elif status["status"] == "failed":
            raise RuntimeError(f"Job failed: {status.get('error')}")

        time.sleep(2)

    raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")


def get_report(job_id: str) -> dict:
    """Get the full report for a completed job."""
    response = requests.get(f"{BASE_URL}/api/report/{job_id}")
    response.raise_for_status()
    return response.json()


def verify_result(case_id: str, report: dict, expected: dict) -> tuple[bool, list[str]]:
    """Verify that the report matches expectations."""
    issues = []

    # Check risk level
    risk_class = report.get("risk_classification")
    if risk_class:
        actual_level = risk_class.get("level", "").lower()
        expected_level = expected["expected_risk_level"]
        if actual_level != expected_level:
            issues.append(f"Risk level: expected {expected_level}, got {actual_level}")
    else:
        # For minimal risk with empty report, check is_prohibited flag
        if expected["expected_risk_level"] == "unacceptable":
            if not report.get("is_prohibited"):
                issues.append("Expected prohibited flag but not set")
        elif expected["expected_risk_level"] not in ["minimal", "limited"]:
            issues.append(f"Missing risk_classification")

    # Check requirements count
    req_count = len(report.get("requirements", []))
    min_req, max_req = expected["expected_requirements_range"]
    if not (min_req <= req_count <= max_req):
        issues.append(
            f"Requirements count: expected {min_req}-{max_req}, got {req_count}"
        )

    # Check for errors
    errors = report.get("processing_errors", [])
    if errors:
        issues.append(f"Processing errors: {errors}")

    return len(issues) == 0, issues


def main():
    print("=" * 70)
    print("TERE4AI MVP Test Cases")
    print("=" * 70)
    print()

    # Check API is running
    try:
        response = requests.get(f"{BASE_URL}/health")
        response.raise_for_status()
        print(f"✓ API server is healthy")
    except Exception as e:
        print(f"✗ API server not available: {e}")
        sys.exit(1)

    # Submit all jobs
    print()
    print("Submitting test cases...")
    jobs = {}
    for case_id, case in TEST_CASES.items():
        try:
            job_id = submit_job(case["description"])
            jobs[case_id] = job_id
            print(f"  ✓ {case['name']}: job {job_id[:8]}")
        except Exception as e:
            print(f"  ✗ {case['name']}: {e}")

    # Wait for all jobs to complete
    print()
    print("Waiting for completion...")
    results = {}
    for case_id, job_id in jobs.items():
        case = TEST_CASES[case_id]
        try:
            status = wait_for_job(job_id, timeout=300)
            report = get_report(job_id)
            results[case_id] = {
                "status": status,
                "report": report,
            }
            print(f"  ✓ {case['name']}: completed")
        except Exception as e:
            print(f"  ✗ {case['name']}: {e}")
            results[case_id] = {"error": str(e)}

    # Verify results
    print()
    print("Verifying results...")
    print("=" * 70)

    passed = 0
    failed = 0

    for case_id, case in TEST_CASES.items():
        result = results.get(case_id, {})
        if "error" in result:
            print(f"✗ {case['name']}: {result['error']}")
            failed += 1
            continue

        report = result.get("report", {})
        success, issues = verify_result(case_id, report, case)

        if success:
            print(f"✓ {case['name']}")
            passed += 1

            # Print summary
            risk_class = report.get("risk_classification", {})
            level = risk_class.get("level", "unknown") if risk_class else "unknown"
            req_count = len(report.get("requirements", []))
            print(f"    Risk level: {level}")
            print(f"    Requirements: {req_count}")
        else:
            print(f"✗ {case['name']}")
            failed += 1
            for issue in issues:
                print(f"    - {issue}")

    # Summary
    print()
    print("=" * 70)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
