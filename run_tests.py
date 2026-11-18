#!/usr/bin/env python3
"""Quick test runner to verify all tests pass."""

import subprocess
import sys

def run_tests():
    """Run pytest with basic configuration."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-v",
        "--tb=short"
    ]

    print("Running tests...")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 80)

    result = subprocess.run(cmd, cwd=".")

    return result.returncode

if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)

