#!/usr/bin/env python
"""Run tests with diagnostic logging to identify response error sources.

This script runs existing tests and captures diagnostic output to determine whether
generic responses come from moderation, routing, context loss, language handling, or LLM prompt.
"""

import sys
import subprocess
import os

# Set environment for testing
test_env = os.environ.copy()
test_env["LANGUAGE_MODE"] = "event_en_ar_hi_zh"

print("=" * 80)
print("DIAGNOSTIC TEST RUN - Response Error Analysis")
print("=" * 80)
print()
print("Running tests with diagnostic logging...")
print("Watch for [ROUTE], [SAFETY], and [MOD] tags to identify response sources")
print()
print("=" * 80)
print()

test_commands = [
    ("Regression tests (main issues)", 
     ["python", "-m", "pytest", "tests/test_boss_question_regressions.py", "-v", "--tb=short"]),
    
    ("Live info routing tests", 
     ["python", "-m", "pytest", "tests/test_live_info_routing.py", "-v", "--tb=short"]),
    
    ("Live info session tests", 
     ["python", "-m", "pytest", "tests/test_live_info_session.py", "-v", "--tb=short"]),
]

results = {}

for test_name, cmd in test_commands:
    print(f"\n{'='*80}")
    print(f"Running: {test_name}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*80}\n")
    
    try:
        result = subprocess.run(cmd, env=test_env, capture_output=False, text=True)
        results[test_name] = "PASSED" if result.returncode == 0 else "FAILED"
    except Exception as e:
        print(f"Error running test: {e}")
        results[test_name] = "ERROR"
    
    print()

print("\n" + "=" * 80)
print("DIAGNOSTIC TEST RESULTS SUMMARY")
print("=" * 80)
print()

for test_name, status in results.items():
    status_symbol = "✓" if status == "PASSED" else "✗" if status == "FAILED" else "?"
    print(f"{status_symbol} {test_name}: {status}")

print()
print("=" * 80)
print("ANALYSIS GUIDE")
print("=" * 80)
print("""
Look for these diagnostic tags in the output:

[ROUTE] tags show which code path produced the response:
  - [ROUTE] UNCLEAR_TRANSCRIPT_PATH
  - [ROUTE] EVENT_MODE_UNSUPPORTED_LANGUAGE_PATH
  - [ROUTE] UNCERTAIN_LANGUAGE_PATH
  - [ROUTE] TRANSCRIPT_BLOCKED_PATH
  - [ROUTE] LANGUAGE_POLICY_PATH
  - [ROUTE] MIXED_THERE_UNRESOLVED_PATH
  - [ROUTE] LOCATION_CLARIFICATION_PATH
  - [ROUTE] TRANSLATION_PATH
  - [ROUTE] LLM_NORMAL_PATH  (main path for normal responses)

[SAFETY] tags show moderation decisions:
  - [SAFETY] MODERATION_PASS = Response approved by safety check
  - [SAFETY] MODERATION_FLAG = Response flagged and replaced with fallback
  - [SAFETY] MODERATION_ERROR = Network/API error, fallback used
  - [SAFETY] EMERGENCY_BLOCK = Explicitly blocked content

[MOD] tags in the route diagnostics show:
  - Which LLM response was sent to safety check
  - Whether it passed or failed
  - What fallback was used if blocked

DIAGNOSIS:
1. If you see "[ROUTE] LLM_NORMAL_PATH" but get fallback:
   → Issue is in check_reply() or moderation
   
2. If you see "[ROUTE] [non-LLM-path]":
   → Issue is routing - request went to wrong handler
   
3. If you see "[SAFETY] MODERATION_FLAG":
   → LLM response was blocked by moderation as flagged
   
4. If you see "[SAFETY] MODERATION_ERROR":
   → Network error caused fallback
   
5. If you see no [ROUTE] tag:
   → Response came from even earlier path (before diagnostics added)
""")

print("\n" + "=" * 80)
