#!/usr/bin/env python
"""Test script to verify all 5 tools work correctly with the LangGraph agent."""

from agent import run_chat
import json

print("=" * 70)
print("TESTING 5 LANGGRAPH TOOLS")
print("=" * 70)

# Test 1: Search for specific doctor
print("\n[TEST 1] Query: 'What did I talk about with Dr. Sharma last time?'")
result = run_chat("What did I talk about with Dr. Sharma last time?", session_id="test_search")
print(json.dumps(result, indent=2))

# Test 2: List all recent interactions
print("\n[TEST 2] Query: 'Show me the 10 most recent interactions.'")
result = run_chat("Show me the 10 most recent interactions.", session_id="test_list")
print(json.dumps(result, indent=2))

# Test 3: Log new interaction
print("\n[TEST 3] Query: 'Log an interaction with Dr. Johnson about hypertension management'")
result = run_chat("Log an interaction with Dr. Johnson about hypertension management", session_id="test_log")
print(json.dumps(result, indent=2))

# Test 4: Edit interaction (if we have an ID from logging)
print("\n[TEST 4] Query: 'Update the interaction with ID 1 and change the summary to new info'")
result = run_chat("Update the interaction with ID 1 and change the summary to new info", session_id="test_edit")
print(json.dumps(result, indent=2))

# Test 5: Delete interaction
print("\n[TEST 5] Query: 'Remove the interaction with ID 999'")
result = run_chat("Remove the interaction with ID 999", session_id="test_delete")
print(json.dumps(result, indent=2))

print("\n" + "=" * 70)
print("ALL TESTS COMPLETED")
print("=" * 70)
