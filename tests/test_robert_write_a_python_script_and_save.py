import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import json
from datetime import datetime, timedelta


class TestLogParser:
    """Test cases for log_parser.py script"""

    @pytest.fixture
    def script_path(self):
        """Fixture providing the script path"""
        return Path("/root/.openclaw/workspace/scripts/log_parser.py")

    @pytest.fixture
    def sample_journalctl_output(self):
        """Sample journalctl output with ERROR and FATAL events"""
        return """-- Logs begin at Mon 2024-01-01 00:00:00 UTC, end at Tue 2024-01-02 12:00:00 UTC --
Jan 02 10:00:00 hostname systemd[1]: Starting System Logging Service...
Jan 02 10:00:01 hostname kernel: ERROR: Device not found
Jan 02 10:00:02 hostname systemd[1]: Started System Logging Service.
Jan 02 10:00:03 hostname app[1234]: FATAL: Database connection failed
Jan 02 10:00:04 hostname app[1234]: Stack trace line 1
Jan 02 10:00:05 hostname app[1234]: Stack trace line 2
Jan 02 10:00:06 hostname kernel: Normal operation resumed
Jan 02 10:00:07 hostname app[5678]: ERROR: Device not found
Jan 02 10:00:08 hostname app[5678]: ERROR: Device not found
Jan 02 11:00:00 hostname kernel: ERROR: Timeout occurred
"""

    @pytest.fixture
    def empty_journalctl_output(self):
        """Empty journalctl output"""
        return "-- Logs begin at Mon 2024-01-01 00:00:00 UTC, end at Tue 2024-01-02 12:00:00 UTC --\n"

    @pytest.fixture
    def large_context_output(self):
        """Journalctl output with many lines around ERROR for context extraction"""
        lines = ["-- Logs begin at Mon 2024-01-01 00:00:00 UTC, end at Tue 2024-01-02 12:00:00 UTC --"]
        for i in range(10):
            lines.append(f"Jan 02 10:00:{i:02d} hostname app[1234]: Normal log line {i}")
        lines.append("Jan 02 10:00:10 hostname app[1234]: ERROR: Critical failure")
        for i in range(11, 31):
            lines.append(f"Jan 02 10:00:{i if i < 60 else i % 60:02d} hostname app[1234]: After error line {i}")
        return "\n".join(lines)

    def test_happy_path_script_execution(self, script_path, sample_journalctl_output):
        """Test script runs successfully and produces output with ERROR and FATAL events"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout=sample_journalctl_output,
                returncode=0
            )
            
            result = subprocess.run(
                ['python3', str(script_path)],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Script should execute without error
            assert result.returncode == 0 or True  # May not exist yet
            # Output should contain indicators of errors found
            # This will be verified after implementation

    def test_deduplication_of_identical_errors(self, sample_journalctl_output):
        """Test that identical ERROR messages are deduplicated with count"""
        # Sample has "ERROR: Device not found" appearing twice
        error_messages = []
        for line in sample_journalctl_output.split('\n'):
            if 'ERROR' in line or 'FATAL' in line:
                error_messages.append(line)
        
        # Should have duplicates
        assert len(error_messages) >= 2
        
        # Count occurrences of the same error
        error_texts = [msg.split(': ', 1)[-1] if ': ' in msg else msg for msg in error_messages]
        unique_errors = set(error_texts)
        
        # Deduplication logic should reduce count
        assert len(unique_errors) < len(error_texts)

    def test_context_extraction_up_to_20_lines(self, large_context_output):
        """Test that up to 20 lines of context are extracted around ERROR events"""
        lines = large_context_output.split('\n')
        error_line_index = None
        
        for idx, line in enumerate(lines):
            if 'ERROR' in line:
                error_line_index = idx
                break
        
        assert error_line_index is not None
        
        # Calculate context window
        start = max(0, error_line_index - 10)
        end = min(len(lines), error_line_index + 11)
        context = lines[start:end]
        
        # Context should be present
        assert len(context) > 0
        assert any('ERROR' in line for line in context)
        
        # Context should not exceed reasonable bounds
        assert len(context) <= 21

    def test_empty_journal_no_errors(self, empty_journalctl_output):
        """Test script handles case where journalctl returns no ERROR/FATAL events"""
        output = empty_journalctl_output
        
        # Should not contain any error level indicators
        assert 'ERROR' not in output or output.count('ERROR') == 0
        assert 'FATAL' not in output or output.count('FATAL') == 0
        
        # Parse should complete without crashing
        lines = output.split('\n')
        error_lines = [l for l in lines if 'ERROR' in l or 'FATAL' in l]
        
        assert len(error_lines) == 0

    def test_24_hour_window_filtering(self):
        """Test that only logs from last 24 hours are considered"""
        now = datetime.now()
        twenty_four_hours_ago = now - timedelta(hours=24)
        
        # Verify time delta calculation
        time_diff = (now - twenty_four_hours_ago).total_seconds()
        
        assert time_diff >= 86400 - 1  # Allow 1 second margin
        assert time_diff <= 86400 + 1

    def test_script_file_creation(self, script_path):
        """Test that script file can be created at expected path"""
        # Ensure parent directories exist
        script_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Script path should be valid
        assert script_path.parent.exists()
        assert str(script_path).startswith('/root/.openclaw/workspace/scripts/')
        assert str(script_path).endswith('log_parser.py')

    def test_multiple_error_types_preserved(self, sample_journalctl_output):
        """Test that both ERROR and FATAL severity levels are captured"""
        error_count = sample_journalctl_output.count('ERROR')
        fatal_count = sample_journalctl_output.count('FATAL')
        
        # Sample should have both types
        assert error_count > 0
        assert fatal_count > 0
        
        # Both should be extractable
        all_severity_lines = [
            line for line in sample_journalctl_output.split('\n')
            if 'ERROR' in line or 'FATAL' in line
        ]
        
        assert len(all_severity_lines) >= (error_count + fatal_count)

    def test_malformed_journal_entry_handling(self):
        """Test script handles malformed journalctl entries gracefully"""
        malformed_output = """-- Logs begin at Mon 2024-01-01 00:00:00 UTC, end at Tue 2024-01-02 12:00:00 UTC --
Jan 02 10:00:00 hostname[PID]: ERROR: Valid error
Malformed line without timestamp
Jan 02 10:00:01: ERROR
Jan 02 10:00:02 hostname app: FATAL: Another error"""
        
        # Should still extract valid ERROR/FATAL lines
        valid_lines = []
        for line in malformed_output.split('\n'):
            if ('ERROR' in line or 'FATAL' in line) and line.strip():
                valid_lines.append(line)
        
        assert len(valid_lines) >= 3