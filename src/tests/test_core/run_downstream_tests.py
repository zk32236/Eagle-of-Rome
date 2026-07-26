"""
Temporary runner for DOWNSTREAM-20260725 v2 test verification.
Imports and runs the three target test functions, capturing their print() output.
"""
import sys
import os
import io

# Ensure project root is on path
project_root = "/mnt/c/Users/Kerl/PycharmProjects/Eagle of Rome"
sys.path.insert(0, project_root)

# Change to project root
os.chdir(project_root)

# Import the test module
from tests.test_core import test_game_state

# Run each test function
results = {}
for test_name in [
    "test_contract_expiration_file_logging",
    "test_governor_transition_file_logging",
    "test_truce_expiry_file_logging",
]:
    print(f"\n{'='*70}")
    print(f"RUNNING: {test_name}")
    print(f"{'='*70}")
    sys.stdout.flush()

    # Capture stdout
    old_stdout = sys.stdout
    captured = io.StringIO()
    sys.stdout = captured

    try:
        getattr(test_game_state, test_name)()
        results[test_name] = {"status": "PASSED", "error": None}
    except Exception as e:
        import traceback
        results[test_name] = {"status": "FAILED", "error": str(e), "traceback": traceback.format_exc()}
    finally:
        sys.stdout = old_stdout
        output = captured.getvalue()
        print(output)
        if results[test_name]["status"] == "FAILED":
            print(f"ERROR: {results[test_name]['error']}")
            print(f"TRACEBACK:\n{results[test_name]['traceback']}")

print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
for name, result in results.items():
    print(f"  {name}: {result['status']}")

if any(r['status'] == 'FAILED' for r in results.values()):
    sys.exit(1)
