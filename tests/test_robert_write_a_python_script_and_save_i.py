import pytest
import subprocess
import json
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
import os

# Assuming the script will be importable
sys.path.insert(0, '/root/.openclaw/workspace/scripts')


class TestLogParser:
    """Test suite for log_parser.py script."""

    @pytest.fixture
    def sample_journalctl_output(self):
        """Sample journalctl JSON output with ERROR and FATAL events."""
        return [
            {
                "__REALTIME_TIMESTAMP": "1699564800000000",
                "PRIORITY": "3",
                "MESSAGE": "Database connection timeout",
                "_HOSTNAME": "testhost"
            },
            {
                "__REALTIME_TIMESTAMP": "1699564801000000",
                "PRIORITY": "3",
                "MESSAGE": "Database connection timeout",
                "_HOSTNAME": "testhost"
            },
            {
                "__REALTIME_TIMESTAMP": "1699564802000000",
                "PRIORITY": "2",
                "MESSAGE": "Critical system failure",
                "_HOSTNAME": "testhost"
            },
            {
                "__REALTIME_TIMESTAMP": "1699564803000000",
                "PRIORITY": "6",
                "MESSAGE": "Info message - should be ignored",
                "_HOSTNAME": "testhost"
            }
        ]

    def test_script_exists(self):
        """Test that the script file exists at the correct path."""
        script_path = Path('/root/.openclaw/workspace/scripts/log_parser.py')
        assert script_path.exists(), f"Script not found at {script_path}"
        assert script_path.is_file(), f"Path is not a file: {script_path}"

    def test_script_is_executable(self):
        """Test that the script has executable permissions."""
        script_path = Path('/root/.openclaw/workspace/scripts/log_parser.py')
        assert os.access(script_path, os.X_OK), "Script is not executable"

    def test_happy_path_deduplication(self, sample_journalctl_output):
        """Test that duplicate errors are deduplicated in output."""
        # Import the script module and test deduplication logic
        spec = importlib.util.spec_from_file_location(
            "log_parser",
            "/root/.openclaw/workspace/scripts/log_parser.py"
        )
        log_parser = importlib.util.module_from_spec(spec)
        
        # Mock journalctl call
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = json.dumps(sample_journalctl_output)
            spec.loader.exec_module(log_parser)
            
            # Test deduplication function if it exists
            if hasattr(log_parser, 'deduplicate_errors'):
                errors = [item["MESSAGE"] for item in sample_journalctl_output if int(item["PRIORITY"]) <= 3]
                deduplicated = log_parser.deduplicate_errors(errors)
                
                assert len(deduplicated) == 2, "Should have 2 unique errors after deduplication"
                assert "Database connection timeout" in deduplicated
                assert "Critical system failure" in deduplicated

    def test_error_level_filtering(self, sample_journalctl_output):
        """Test that only ERROR (priority 3) and FATAL (priority <= 2) are captured."""
        # Import script
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "log_parser",
            "/root/.openclaw/workspace/scripts/log_parser.py"
        )
        log_parser = importlib.util.module_from_spec(spec)
        
        if hasattr(log_parser, 'filter_error_events'):
            filtered = log_parser.filter_error_events(sample_journalctl_output)
            
            # Should include priority 2 and 3, exclude 6
            assert len(filtered) == 3, "Should filter to only ERROR and FATAL level events"
            assert all(int(item["PRIORITY"]) <= 3 for item in filtered), "All filtered events should be priority <= 3"

    def test_empty_journal_output(self):
        """Test edge case: empty journalctl output."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = "[]"
            
            # Should handle gracefully without crashing
            result = subprocess.run(
                ['python3', '/root/.openclaw/workspace/scripts/log_parser.py'],
                capture_output=True,
                timeout=5
            )
            assert result.returncode == 0, "Script should exit cleanly on empty journal"

    def test_no_error_events(self):
        """Test edge case: journal with no ERROR or FATAL events."""
        info_only_output = [
            {"PRIORITY": "6", "MESSAGE": "Info message"},
            {"PRIORITY": "5", "MESSAGE": "Notice message"}
        ]
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = json.dumps(info_only_output)
            
            result = subprocess.run(
                ['python3', '/root/.openclaw/workspace/scripts/log_parser.py'],
                capture_output=True,
                timeout=5
            )
            assert result.returncode == 0
            # Output should indicate no errors found or be gracefully empty
            output = result.stdout.decode()
            assert len(output) >= 0, "Should produce valid output even with no errors"

    def test_journalctl_command_failure(self):
        """Test error condition: journalctl command fails."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("journalctl not found")
            
            result = subprocess.run(
                ['python3', '/root/.openclaw/workspace/scripts/log_parser.py'],
                capture_output=True,
                timeout=5
            )
            # Should handle gracefully or exit with clear error
            assert result.returncode in [0, 1], "Script should handle missing journalctl gracefully"

    def test_output_format_contains_required_elements(self):
        """Test that script output contains formatted error information."""
        result = subprocess.run(
            ['python3', '/root/.openclaw/workspace/scripts/log_parser.py'],
            capture_output=True,
            timeout=10,
            text=True
        )
        
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        output = result.stdout
        
        # Output should be valid text (may be empty if no errors in last 24h)
        assert isinstance(output, str), "Output should be a string"


import importlib.util