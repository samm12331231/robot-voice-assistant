# Response Error Diagnostic Guide

## What Was Added

Safe diagnostic logging that shows:
- Which code path produced the response ([ROUTE])
- Whether moderation was called and what it decided ([SAFETY])
- What LLM generated vs what was returned
- Where generic responses come from

---

## How to Run Diagnostics

### Quick Test (Recommended)
```bash
python test_response_diagnostics.py
```

### Run All Tests
```bash
python run_diagnostic_tests.py
```

### Manual Test
```bash
python main.py --text "Your question"
```

---

## Diagnostic Output Tags

### [ROUTE] - Code Path

Appears before the response:

```
[ROUTE] LLM_NORMAL_PATH              → Normal question path
[ROUTE] UNCLEAR_TRANSCRIPT_PATH      → Input too unclear
[ROUTE] UNCERTAIN_LANGUAGE_PATH      → Language detection failed
[ROUTE] TRANSCRIPT_BLOCKED_PATH      → Safety blocked input
[ROUTE] LANGUAGE_POLICY_PATH         → Event language policy
[ROUTE] LOCATION_CLARIFICATION_PATH  → Location clarification
[ROUTE] TRANSLATION_PATH             → Translation handler
[ROUTE] MIXED_THERE_UNRESOLVED_PATH  → "There" unresolvable
```

### [SAFETY] - Moderation Result

```
[SAFETY] MODERATION_PASS             → Response approved
  Reply: "2 + 2 = 4..."

[SAFETY] MODERATION_FLAG             → Response blocked
  LLM reply: "Here's how to..."
  Fallback: "I'm here to help..."

[SAFETY] MODERATION_ERROR            → Network error
  Network fallback used

[SAFETY] EMERGENCY_BLOCK             → Explicit block triggered
```

---

## Diagnosis Flowchart

If you get generic response:

1. **Look for [ROUTE]**
   - If not present → Early routing issue
   - If `LLM_NORMAL_PATH` → Go to step 2
   - If other → Routed to alternative handler

2. **Look for [SAFETY]**
   - If `MODERATION_FLAG` → **Moderation is blocking**
   - If `MODERATION_PASS` → **LLM generated generic**
   - If `MODERATION_ERROR` → **Network error**
   - If not present → **Context lost or early issue**

---

## Root Causes

### 1. Moderation Fallback
**Sign:** `[SAFETY] MODERATION_FLAG`  
**Cause:** Moderation flagged LLM response  
**Why:** Keywords like "violence", "weapon" etc.  
**Fix:** Adjust moderation or trust LLM safety more  

### 2. Wrong Routing
**Sign:** `[ROUTE]` shows non-LLM path  
**Cause:** Routing logic misdirected  
**Why:** Language/clarity detection failed  
**Fix:** Debug routing conditions  

### 3. Lost Context
**Sign:** `[SAFETY] MODERATION_PASS` but generic response  
**Cause:** LLM generated generic  
**Why:** Context missing or session empty  
**Fix:** Check SESSION_STATE["history"]  

### 4. Language Issue
**Sign:** `[ROUTE] UNCERTAIN_LANGUAGE_PATH`  
**Cause:** Language detection failed  
**Why:** Ambiguous input  
**Fix:** Improve language detection  

### 5. LLM Prompt
**Sign:** Correct route, no flag, but generic  
**Cause:** LLM following overly-cautious prompt  
**Why:** System prompt too conservative  
**Fix:** Adjust llm.py lines 96-121  

---

## Example: Generic Response

```
[ROUTE] LLM_NORMAL_PATH
[SAFETY] MODERATION_FLAG (reply truncated to 80 chars)
[SAFETY]   LLM reply: "Here's how to defend yourself by exerc..."
[SAFETY]   Fallback:  "I'm here to help. What would you..."
Assistant: I'm here to help. What would you like to know?
```

**Analysis:**
- Routed correctly
- LLM gave good response  
- Moderation flagged it
- Fallback returned

**Root Cause:** Moderation too aggressive

---

## Safety Notes

✅ No bypass of safety  
✅ No full harmful text logged  
✅ No API keys logged  
✅ Fail-closed behavior unchanged  
✅ Only added visibility

