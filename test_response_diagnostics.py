#!/usr/bin/env python
"""Quick diagnostic test to identify response error sources.

Run: python test_response_diagnostics.py

This runs a few test cases and shows diagnostic output to identify:
1. Which code path produces the response
2. Whether moderation was called
3. Whether the response was replaced
4. The actual LLM output vs final output
"""

import os
import sys
from io import StringIO
from contextlib import redirect_stdout

# Set event mode for language testing
os.environ["LANGUAGE_MODE"] = "event_en_ar_hi_zh"

print("=" * 90)
print("RESPONSE DIAGNOSTIC TEST")
print("=" * 90)
print()
print("This will run sample requests and show diagnostic information.")
print("Look for [ROUTE] and [SAFETY] tags to understand response sources.")
print()
print("=" * 90)
print()

test_cases = [
    {
        "name": "Simple factual question",
        "prompt": "What is 2 + 2?",
        "language": "en",
        "description": "Should go through LLM_NORMAL_PATH"
    },
    {
        "name": "Joke request",
        "prompt": "Tell me a joke",
        "language": "en",
        "description": "Should go through LLM_NORMAL_PATH, may trigger moderation"
    },
    {
        "name": "Weather request",
        "prompt": "What's the weather in Dubai?",
        "language": "en",
        "description": "Should go through live info path first"
    },
    {
        "name": "Greeting",
        "prompt": "Hello",
        "language": "en",
        "description": "Should go through LLM_NORMAL_PATH"
    },
]

import main

for i, test_case in enumerate(test_cases, 1):
    print(f"\n{'─' * 90}")
    print(f"TEST {i}: {test_case['name']}")
    print(f"{'─' * 90}")
    print(f"Prompt: {test_case['prompt']}")
    print(f"Language: {test_case['language']}")
    print(f"Expected: {test_case['description']}")
    print()
    print("Output:")
    print()
    
    try:
        # Capture stdout to see diagnostics
        captured_output = StringIO()
        with redirect_stdout(captured_output):
            main.run_text_mode(test_case['prompt'])
        
        output = captured_output.getvalue()
        print(output)
        
        # Extract diagnostics from output
        lines = output.split('\n')
        route_line = next((l for l in lines if '[ROUTE]' in l), None)
        safety_lines = [l for l in lines if '[SAFETY' in l or '[MOD]' in l]
        
        print()
        print("DIAGNOSTICS:")
        if route_line:
            print(f"  Route: {route_line}")
        else:
            print("  Route: Not captured (may be early path)")
        
        if safety_lines:
            for sl in safety_lines:
                print(f"  {sl}")
        else:
            print("  Safety: Not called (no diagnostics captured)")
        
    except Exception as e:
        print(f"Error running test: {e}")
        import traceback
        traceback.print_exc()
    
    print()

print()
print("=" * 90)
print("DIAGNOSTIC INTERPRETATION GUIDE")
print("=" * 90)
print("""
For each test, you should see:

1. [ROUTE] tag showing which code path was taken
   - Expected for most normal questions: [ROUTE] LLM_NORMAL_PATH

2. [SAFETY] tag showing moderation result
   - [SAFETY] MODERATION_PASS: Response approved, sent as-is
   - [SAFETY] MODERATION_FLAG: Response flagged and replaced with fallback
   - [SAFETY] MODERATION_ERROR: Network error, fallback used

3. If generic response appears:
   a) Check if [SAFETY] MODERATION_FLAG is present
      → Then moderation is replacing responses
   
   b) Check if [ROUTE] shows non-LLM path
      → Then request was routed incorrectly
   
   c) Check if no diagnostics at all
      → Then issue is before diagnostics (early routing)

WHAT WOULD INDICATE A PROBLEM:
- Many MODERATION_FLAG messages = aggressive moderation blocking
- Seeing wrong [ROUTE] = routing issue
- Generic responses without diagnostics = context/prompt issue
""")

print()
print("=" * 90)
