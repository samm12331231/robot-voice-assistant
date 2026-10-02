#!/usr/bin/env python
"""Quick audit tests for the 8 reported issue categories."""

from language_utils import event_mixed_live_request

print("=" * 80)
print("AUDIT TEST SUITE - Mixed Request Parsing")
print("=" * 80)

# Test Case 1: Comma without "the"
print("\n[TEST 1] Comma-separated without explicit 'the':")
test1 = event_mixed_live_request('Tell me the weather in Dubai in Arabic, time in Tokyo in Hindi.')
print(f"  Input: 'Tell me the weather in Dubai in Arabic, time in Tokyo in Hindi.'")
print(f"  Result: {test1}")
print(f"  Expected: ('dubai', ('weather', 'ar'), 'tokyo', ('time', 'hi'))")
print(f"  ✓ PASS" if test1 == ('dubai', ('weather', 'ar'), 'tokyo', ('time', 'hi')) else f"  ✗ FAIL")

# Test Case 2: One language specified, one not
print("\n[TEST 2] One language specified, one not:")
test2 = event_mixed_live_request('Tell me the weather in Dubai in Arabic and the time in Tokyo.')
print(f"  Input: 'Tell me the weather in Dubai in Arabic and the time in Tokyo.'")
print(f"  Result: {test2}")
print(f"  Expected: ('dubai', ('weather', 'ar'), 'tokyo', ('time', 'en'))")
print(f"  ✓ PASS" if test2 == ('dubai', ('weather', 'ar'), 'tokyo', ('time', 'en')) else f"  ✗ FAIL")

# Test Case 3: Shared location without explicit language
print("\n[TEST 3] Shared location, no explicit language:")
test3 = event_mixed_live_request('Tell me the weather and the time in Dubai.')
print(f"  Input: 'Tell me the weather and the time in Dubai.'")
print(f"  Result: {test3}")
print(f"  Expected: ('dubai', ('weather', 'en'), 'dubai', ('time', 'en'))")
print(f"  ✓ PASS" if test3 == ('dubai', ('weather', 'en'), 'dubai', ('time', 'en')) else f"  ✗ FAIL")

# Test Case 4: There in first clause without prior context
print("\n[TEST 4] 'There' in first clause without prior context:")
test4 = event_mixed_live_request('What is the weather there in Arabic, and the time in Dubai in Hindi?')
print(f"  Input: 'What is the weather there in Arabic, and the time in Dubai in Hindi?'")
print(f"  Result: {test4}")
print(f"  Expected: None (should fail gracefully)")
if test4 is None:
    print(f"  ✓ PASS - Returns None as expected")
else:
    print(f"  ✗ FAIL - Should return None, got {test4}")

# Test Case 5: Comma with "or"
print("\n[TEST 5] Comma with 'or' conjunction:")
test5 = event_mixed_live_request('Tell me the weather in Dubai in Arabic, or the time in Tokyo in Hindi.')
print(f"  Input: 'Tell me the weather in Dubai in Arabic, or the time in Tokyo in Hindi.'")
print(f"  Result: {test5}")
print(f"  Expected: ('dubai', ('weather', 'ar'), 'tokyo', ('time', 'hi'))")
print(f"  ✓ PASS" if test5 == ('dubai', ('weather', 'ar'), 'tokyo', ('time', 'hi')) else f"  ✗ FAIL")

# Test Case 6: Comma with "then"
print("\n[TEST 6] Comma with 'then' conjunction:")
test6 = event_mixed_live_request('Tell me the weather in Dubai in Arabic, then the time in Tokyo in Hindi.')
print(f"  Input: 'Tell me the weather in Dubai in Arabic, then the time in Tokyo in Hindi.'")
print(f"  Result: {test6}")
print(f"  Expected: ('dubai', ('weather', 'ar'), 'tokyo', ('time', 'hi'))")
print(f"  ✓ PASS" if test6 == ('dubai', ('weather', 'ar'), 'tokyo', ('time', 'hi')) else f"  ✗ FAIL")

# Test Case 7: Both with "there" and remembered location
print("\n[TEST 7] Both clauses use 'there' (requires prior location):")
test7 = event_mixed_live_request('What time is it there in Arabic, and what is the weather there in Hindi?')
print(f"  Input: 'What time is it there in Arabic, and what is the weather there in Hindi?'")
print(f"  Result: {test7}")
print(f"  Expected: None (no prior location to resolve 'there')")
if test7 is None:
    print(f"  ✓ PASS - Returns None as expected")
else:
    print(f"  ✗ FAIL - Should return None, got {test7}")

print("\n" + "=" * 80)
print("AUDIT TEST SUMMARY")
print("=" * 80)
