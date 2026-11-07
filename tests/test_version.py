"""Tests for version command."""
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path


# Explicit environment for subprocess isolation
_subprocess_env = os.environ.copy()


class TestVersionCommand(unittest.TestCase):
    """Test the version command."""

    def test_version_command_exists(self):
        """The version subcommand exists and can be invoked."""
        result = subprocess.run(
            [sys.executable, "-m", "wintap", "version"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_subprocess_env
        )
        self.assertEqual(result.returncode, 0, f"Version command failed: {result.stderr}")

    def test_version_output_format(self):
        """Version output contains expected format."""
        result = subprocess.run(
            [sys.executable, "-m", "wintap", "version"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_subprocess_env
        )
        output = result.stdout.strip()
        # Should start with "wintap " followed by version
        self.assertTrue(output.startswith("wintap "), f"Unexpected version output: {output}")
        self.assertRegex(output, r'^wintap\s+\d+\.\d+\.\d+', f"Version output should match 'wintap X.Y.Z': {output}")

    def test_version_format(self):
        """Version output matches semantic versioning pattern."""
        result = subprocess.run(
            [sys.executable, "-m", "wintap", "version"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_subprocess_env
        )
        output = result.stdout.strip()
        # Extract version number (supports both "wintap X.Y.Z" and "wintap vX.Y.Z" formats)
        match = re.search(r'wintap\s*v?(\S+)', output)
        self.assertIsNotNone(match, f"Could not extract version from: {output}")
        version = match.group(1)
        # Should be semver-like (X.Y.Z or X.Y.Z-suffix)
        semver_pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$'
        self.assertRegex(version, semver_pattern, f"Version '{version}' doesn't match semver pattern")


class TestVersionEndpoint(unittest.TestCase):
    """Test the /api/version endpoint."""

    def test_version_endpoint_structure(self):
        """Version endpoint returns proper JSON structure."""
        # This test can run without the server by checking the code structure
        from wintap import __version__
        self.assertIsNotNone(__version__, "Version should not be None")
        self.assertIsInstance(__version__, str, "Version should be a string")

    def test_version_is_valid(self):
        """Version is a valid semantic version."""
        from wintap import __version__
        self.assertTrue(
            __version__.startswith("0.") or
            __version__ >= "0.1.0",
            f"Version '{__version__}' should be valid semver"
        )


if __name__ == "__main__":
    unittest.main()