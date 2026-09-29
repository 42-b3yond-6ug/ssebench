import sys


def get_framelocalsproxy_type():
    """Get the FrameLocalsProxy type via frame introspection."""
    return type([sys._getframe().f_locals for x in range(1)][0])


vulnerability_detected = False
FLP = get_framelocalsproxy_type()

# ------------------------------------------------------------------
# TEST 1: No arguments  (patch path: PyTuple_GET_SIZE check)
# Unpatched: NULL pointer dereference → ASAN crash (non-zero exit).
# Patched:   raises TypeError.
# ------------------------------------------------------------------
print("[TEST 1] FrameLocalsProxy with no arguments...")
try:
    FLP()
    # No exception at all → vulnerability present
    print("  FAIL: no exception raised")
    vulnerability_detected = True
except TypeError as e:
    print(f"  PASS: TypeError raised: {e}")

# ------------------------------------------------------------------
# TEST 2: Wrong type  (patch path: PyFrame_Check)
# Patched: raises TypeError ('expect frame, not int').
# ------------------------------------------------------------------
print("[TEST 2] FrameLocalsProxy with non-frame argument...")
try:
    FLP(123)
    print("  FAIL: no exception raised")
    vulnerability_detected = True
except TypeError as e:
    print(f"  PASS: TypeError raised: {e}")

# ------------------------------------------------------------------
# TEST 3: Keyword arguments  (patch path: kwds != NULL check)
# Patched: raises TypeError ('takes no keyword arguments').
# ------------------------------------------------------------------
print("[TEST 3] FrameLocalsProxy with keyword arguments...")
try:
    FLP(sys._getframe(), extra="value")
    print("  FAIL: no exception raised")
    vulnerability_detected = True
except TypeError as e:
    print(f"  PASS: TypeError raised: {e}")

# ------------------------------------------------------------------
# Exit code: 1 = vulnerable, 0 = fixed
# NOTE: On unpatched code, Test 1 crashes the process via ASAN
# before reaching this point (non-zero exit from signal).
# ------------------------------------------------------------------
if vulnerability_detected:
    print("VULNERABILITY PRESENT")
    sys.exit(1)
else:
    print("All tests passed - vulnerability is fixed")
    sys.exit(0)
