"""Run the full Task 0.3 validation and print a pass/fail report."""

from chemomech.validate import validate

results = validate()
print()
print("=== Validation results ===")
allpass = True
for r in results:
    allpass = allpass and r.passed
    status = "PASS" if r.passed else "FAIL"
    print(f"[{status}] {r.name}: {r.detail}")
print()
print("ALL PASSED:", allpass)