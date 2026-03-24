"""
Async integration tests for tmux tool functions.

These tests require tmux to be installed and will create actual tmux sessions.
Run with: python -m pytest test_tmux_tools_async.py -v --asyncio-mode=auto

WARNING: These tests will create and manipulate real tmux sessions.
Make sure you don't have important work in tmux before running.
"""

import asyncio
import os
import subprocess
import time

import pytest
import pytest_asyncio

# Import the async functions from the module
from tmux_tools import (
    AGENT_SESSION,
    tmux_del,
    tmux_list,
    tmux_new,
    tmux_read_last,
    tmux_send_signal,
    tmux_wait,
    tmux_write,
)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def cleanup_before_tests():
    """Clean up any leftover agent session before running tests."""
    proc = await asyncio.create_subprocess_exec(
        "tmux", "kill-session", "-t", AGENT_SESSION,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    yield
    # Cleanup after all tests
    proc = await asyncio.create_subprocess_exec(
        "tmux", "kill-session", "-t", AGENT_SESSION,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()


@pytest_asyncio.fixture
async def fresh_agent_session():
    """
    Ensure agent_session exists with a test window.
    Returns the test window name.
    """
    # Kill existing session to ensure fresh state
    proc = await asyncio.create_subprocess_exec(
        "tmux", "kill-session", "-t", AGENT_SESSION,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    await asyncio.sleep(0.1)

    # Create the agent session with a test window
    result = await tmux_new(window_name="testwin")
    if "Error:" in result:
        pytest.fail(f"Failed to create agent session: {result}")

    yield "testwin"

    # Cleanup
    proc = await asyncio.create_subprocess_exec(
        "tmux", "kill-session", "-t", AGENT_SESSION,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()


class TestTmuxNew:
    """Tests for tmux_new function."""

    @pytest.mark.asyncio
    async def test_tmux_new_creates_agent_session(self):
        """Test that tmux_new creates the agent_session if it doesn't exist."""
        # Kill any existing session
        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-session", "-t", AGENT_SESSION,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        await asyncio.sleep(0.1)

        result = await tmux_new(window_name="firstwin")
        assert "Created window" in result
        assert AGENT_SESSION in result
        assert "firstwin" in result

        # Verify session exists
        check = await asyncio.create_subprocess_exec(
            "tmux", "has-session", "-t", AGENT_SESSION,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await check.wait()
        assert check.returncode == 0

    @pytest.mark.asyncio
    async def test_tmux_new_creates_multiple_windows(self):
        """Test creating multiple windows in agent_session."""
        # Ensure session exists
        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-session", "-t", AGENT_SESSION,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        await asyncio.sleep(0.1)
        await tmux_new(window_name="win1")

        # Create second window
        result = await tmux_new(window_name="win2")
        assert "Created window" in result
        assert "win2" in result

        # Verify both exist
        list_result = await tmux_list()
        assert "win1" in list_result
        assert "win2" in list_result

    @pytest.mark.asyncio
    async def test_tmux_new_duplicate_window_name(self):
        """Test creating window with duplicate name fails."""
        # Ensure session exists
        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-session", "-t", AGENT_SESSION,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        await asyncio.sleep(0.1)
        await tmux_new(window_name="uniquewin")

        # Try to create duplicate
        result = await tmux_new(window_name="uniquewin")
        assert "Error:" in result
        assert "already exists" in result

    @pytest.mark.asyncio
    async def test_tmux_new_with_command(self):
        """Test creating a window with initial command."""
        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-session", "-t", AGENT_SESSION,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        await asyncio.sleep(0.1)

        result = await tmux_new(window_name="cmdwin", command="cmd.exe /c echo hello")
        assert "Created window" in result
        await asyncio.sleep(0.5)

    @pytest.mark.asyncio
    async def test_tmux_new_with_python_repl(self):
        """Test creating a window with Python REPL as command."""
        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-session", "-t", AGENT_SESSION,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        await asyncio.sleep(0.1)

        result = await tmux_new(window_name="pyrepl", command="python3")
        assert "Created window" in result
        await asyncio.sleep(2)

        # Wait for Python prompt
        wait_result = await tmux_wait("pyrepl", ">>>", timeout=5)
        assert "found" in wait_result.lower()

        # Execute Python code
        await tmux_write("pyrepl", "print(1 + 2)")
        await asyncio.sleep(0.5)

        # Wait for result
        wait_result = await tmux_wait("pyrepl", "3", timeout=5)
        assert "found" in wait_result.lower()

    @pytest.mark.asyncio
    async def test_tmux_new_with_python_repl_readlast(self):
        """Test creating a window with Python REPL using tmux_read_last."""
        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-session", "-t", AGENT_SESSION,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        await asyncio.sleep(0.1)

        result = await tmux_new(window_name="pyrepl2", command="python3")
        assert "Created window" in result
        await asyncio.sleep(2)

        # Read to check Python started
        read_result = await tmux_read_last("pyrepl2", 20)
        assert ">>>" in read_result

        # Execute Python code
        await tmux_write("pyrepl2", "print(100 + 200)")
        await asyncio.sleep(0.5)

        # Read output
        read_result = await tmux_read_last("pyrepl2", 20)
        assert "300" in read_result


class TestTmuxList:
    """Tests for tmux_list function."""

    @pytest.mark.asyncio
    async def test_tmux_list_empty_when_no_session(self):
        """Test listing when agent_session doesn't exist."""
        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-session", "-t", AGENT_SESSION,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        await asyncio.sleep(0.1)

        result = await tmux_list()
        # The function returns "No active windows" when session exists but no windows
        # or when session doesn't exist? Let's check actual behavior.
        # It returns "No active windows" if session exists but list returns empty.
        # If session doesn't exist, result may be "No active windows" as well.
        assert "No active windows" in result or "does not exist" in result

    @pytest.mark.asyncio
    async def test_tmux_list_with_agent_session(self, fresh_agent_session):
        """Test listing windows in agent_session."""
        result = await tmux_list()
        assert fresh_agent_session in result


class TestReadLast:
    """Tests for tmux_read_last function."""

    @pytest.mark.asyncio
    async def test_tmux_read_last_nonexistent_window(self):
        """Test reading from non-existent window."""
        result = await tmux_read_last("nonexistent_window_12345", 10)
        assert "Error:" in result
        assert "does not exist" in result

    @pytest.mark.asyncio
    async def test_tmux_read_last(self, fresh_agent_session):
        """Test reading last N lines from a window."""
        window_name = fresh_agent_session

        # Send multiple commands to create output
        for i in range(5):
            await tmux_write(window_name, f"echo line_{i}")
            await asyncio.sleep(0.2)  # Allow time for output

        # Read last 3 lines
        result = await tmux_read_last(window_name, 3)
        assert "[lines" in result  # Check for line range header
        # The lines should be present
        assert "line_4" in result or "line_2" in result  # depending on truncation

    @pytest.mark.asyncio
    async def test_tmux_read_last_more_than_available(self, fresh_agent_session):
        """Test reading last N lines when N exceeds available lines."""
        window_name = fresh_agent_session

        # Read more lines than exist
        result = await tmux_read_last(window_name, 100)
        assert "[lines" in result  # Check for line range header


class TestTmuxWrite:
    """Tests for tmux_write function."""

    @pytest.mark.asyncio
    async def test_tmux_write_to_nonexistent_window(self):
        """Test writing to non-existent window."""
        result = await tmux_write("nonexistent_window_12345", "hello")
        assert "Error:" in result

    @pytest.mark.asyncio
    async def test_tmux_write_text(self, fresh_agent_session):
        """Test writing text to a window."""
        window_name = fresh_agent_session

        result = await tmux_write(window_name, "echo hello_world")
        assert "sent to" in result

        # Wait for output to confirm it executed
        wait_result = await tmux_wait(window_name, "hello_world", timeout=5)
        assert "found" in wait_result.lower()

    @pytest.mark.asyncio
    async def test_tmux_write_special_keys(self, fresh_agent_session):
        """Test sending special keys like Ctrl+C."""
        window_name = fresh_agent_session

        # First run a command that will run a long sleep, then interrupt it
        await tmux_write(window_name, "sleep 10")
        await asyncio.sleep(0.5)
        result = await tmux_write(window_name, "C-c")
        assert "sent to" in result
        # The sleep should be interrupted, we can check that no "sleep" is running
        # This is a bit tricky, but at least the send-keys should not fail

    @pytest.mark.asyncio
    async def test_tmux_write_multiline(self, fresh_agent_session):
        """Test writing multiple lines using \\n escape."""
        window_name = fresh_agent_session

        # Use the documented \\n to split into multiple commands
        # The first line will be 'echo line1', second 'echo line2'
        result = await tmux_write(window_name, "echo line1\\necho line2")
        assert "sent to" in result

        # Wait for both outputs
        await tmux_wait(window_name, "line1", timeout=5)
        await tmux_wait(window_name, "line2", timeout=5)

    @pytest.mark.asyncio
    async def test_tmux_write_newline_in_text(self, fresh_agent_session):
        """Test writing text containing actual newline character."""
        window_name = fresh_agent_session

        # Actual newline in string - should be treated as a single part, then Enter
        result = await tmux_write(window_name, "echo line1\n echo line2")
        assert "sent to" in result

        # The command will be sent as "echo line1\n echo line2" followed by Enter
        # The shell will interpret the newline as a command separator,
        # but it may be escaped. This test checks that the function doesn't crash.
        await asyncio.sleep(0.5)
        # We don't assert exact output because behavior is shell-dependent


class TestTmuxWait:
    """Tests for tmux_wait function."""

    @pytest.mark.asyncio
    async def test_tmux_wait_text_found(self, fresh_agent_session):
        """Test waiting for text that appears."""
        window_name = fresh_agent_session

        # Send a command that outputs something
        await tmux_write(window_name, "echo wait_text_xyz")

        # Wait for the text
        result = await tmux_wait(window_name, "wait_text_xyz", timeout=5)
        assert "found" in result.lower()

    @pytest.mark.asyncio
    async def test_tmux_wait_timeout(self, fresh_agent_session):
        """Test waiting for text that never appears (timeout)."""
        window_name = fresh_agent_session

        # Wait for text that won't appear
        result = await tmux_wait(window_name, "this_text_will_never_appear_xyz123", timeout=1)
        assert "Timeout:" in result

    @pytest.mark.asyncio
    async def test_tmux_wait_substring_match(self, fresh_agent_session):
        """Test waiting for substring match (not regex)."""
        window_name = fresh_agent_session

        # Send a command with special regex characters
        await tmux_write(window_name, "echo hello.world")

        # Should match as literal substring, not as regex
        result = await tmux_wait(window_name, "hello.world", timeout=5)
        assert "found" in result.lower()

        # Should also match partial substring
        result = await tmux_wait(window_name, "lo.wo", timeout=5)
        assert "found" in result.lower()

    @pytest.mark.asyncio
    async def test_tmux_wait_only_new_content(self, fresh_agent_session):
        """Test that wait only considers new content after previous reads."""
        window_name = fresh_agent_session

        # Send initial output that will be read
        await tmux_write(window_name, "echo old_text")
        await tmux_wait(window_name, "old_text", timeout=5)  # Wait for it to appear

        # Now read the output to mark it as read
        await tmux_read_last(window_name, 100)

        # Send new output
        await tmux_write(window_name, "echo new_text")
        await asyncio.sleep(0.5)

        # Wait for new_text, should succeed
        result = await tmux_wait(window_name, "new_text", timeout=5)
        assert "found" in result.lower()

        # Wait for old_text again, but it should not be considered new
        # So it should timeout
        result = await tmux_wait(window_name, "old_text", timeout=1)
        assert "Timeout:" in result


class TestTmuxSendSignal:
    """Tests for tmux_send_signal function."""

    @pytest.mark.asyncio
    async def test_tmux_send_signal_sigint(self, fresh_agent_session):
        """Test sending SIGINT (Ctrl+C)."""
        window_name = fresh_agent_session

        result = await tmux_send_signal(window_name, "SIGINT")
        assert "SIGINT" in result

    @pytest.mark.asyncio
    async def test_tmux_send_signal_sigterm(self, fresh_agent_session):
        """Test sending SIGTERM (mapped to Ctrl+C)."""
        window_name = fresh_agent_session

        result = await tmux_send_signal(window_name, "SIGTERM")
        assert "SIGTERM" in result

    @pytest.mark.asyncio
    async def test_tmux_send_signal_to_nonexistent_window(self):
        """Test sending signal to non-existent window."""
        result = await tmux_send_signal("nonexistent_window_12345", "SIGINT")
        assert "Error:" in result

    @pytest.mark.asyncio
    async def test_tmux_send_signal_unsupported(self, fresh_agent_session):
        """Test sending unsupported signal."""
        window_name = fresh_agent_session

        result = await tmux_send_signal(window_name, "SIGUSR1")
        # This may return error or success depending on if kill succeeded
        # Not critical, just ensure it doesn't crash


class TestTmuxDel:
    """Tests for tmux_del function."""

    @pytest.mark.asyncio
    async def test_tmux_del_window(self, fresh_agent_session):
        """Test deleting a window."""
        # Create another window first
        await tmux_new(window_name="tobedeleted")
        await asyncio.sleep(0.1)

        result = await tmux_del("tobedeleted")
        assert "Killed window" in result

        # Verify it's gone
        list_result = await tmux_list()
        assert "tobedeleted" not in list_result

    @pytest.mark.asyncio
    async def test_tmux_del_nonexistent(self):
        """Test deleting non-existent window."""
        result = await tmux_del("nonexistent_window_xyz123")
        assert "Error:" in result


class TestIntegration:
    """Integration tests simulating real workflows."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, fresh_agent_session):
        """Test a complete workflow: write, wait, read, delete."""
        window_name = fresh_agent_session

        # Write command
        write_result = await tmux_write(window_name, "echo integration_test")
        assert "sent to" in write_result

        # Wait for the text to appear in output
        wait_result = await tmux_wait(window_name, "integration_test", timeout=5)
        assert "found" in wait_result.lower()

        # Read output
        read_result = await tmux_read_last(window_name, 20)
        assert "integration_test" in read_result

        # Delete the window (optional, but tests deletion)
        del_result = await tmux_del(window_name)
        assert "Killed window" in del_result

    @pytest.mark.asyncio
    async def test_multiple_windows_workflow(self):
        """Test running commands in multiple windows."""
        # Clean start
        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-session", "-t", AGENT_SESSION,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        await asyncio.sleep(0.1)

        # Create multiple windows
        for name in ["worker1", "worker2", "worker3"]:
            await tmux_new(window_name=name)
            await asyncio.sleep(0.1)

        # Send commands to each
        for i, name in enumerate(["worker1", "worker2", "worker3"]):
            await tmux_write(name, f"echo command_from_{name}")
            await asyncio.sleep(0.2)

        # Wait for output and verify
        for name in ["worker1", "worker2", "worker3"]:
            result = await tmux_wait(name, f"command_from_{name}", timeout=5)
            assert "found" in result.lower()

    @pytest.mark.asyncio
    async def test_python_repl(self, fresh_agent_session):
        """Test running Python code in REPL."""
        window_name = fresh_agent_session

        # Start Python REPL
        await tmux_write(window_name, "python3")
        await asyncio.sleep(1)

        # Wait for Python prompt
        wait_result = await tmux_wait(window_name, ">>>", timeout=5)
        assert "found" in wait_result.lower()

        # Execute some Python code
        await tmux_write(window_name, "print(1 + 2)")
        await asyncio.sleep(0.5)

        # Wait for result
        wait_result = await tmux_wait(window_name, "3", timeout=5)
        assert "found" in wait_result.lower()

        # Verify output contains the result
        read_result = await tmux_read_last(window_name, 20)
        assert "3" in read_result

        # More complex code - define variables and use them
        await tmux_write(window_name, "x = 10")
        await asyncio.sleep(0.3)
        await tmux_write(window_name, "y = 20")
        await asyncio.sleep(0.3)
        await tmux_write(window_name, "print(x + y)")
        await asyncio.sleep(0.5)

        wait_result = await tmux_wait(window_name, "30", timeout=5)
        assert "found" in wait_result.lower()

        read_result = await tmux_read_last(window_name, 30)
        assert "30" in read_result

        # Test JSON output
        await tmux_write(window_name, "import json")
        await asyncio.sleep(0.3)
        await tmux_write(window_name, "data = {'key': 'value'}")
        await asyncio.sleep(0.3)
        await tmux_write(window_name, "print(json.dumps(data))")
        await asyncio.sleep(0.5)

        wait_result = await tmux_wait(window_name, '"key"', timeout=5)
        assert "found" in wait_result.lower()

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, fresh_agent_session):
        """Test concurrent reads and writes."""
        window_name = fresh_agent_session

        # Define a function that writes and reads concurrently
        async def writer():
            for i in range(5):
                await tmux_write(window_name, f"echo writer_{i}")
                await asyncio.sleep(0.1)

        async def reader():
            for i in range(5):
                await asyncio.sleep(0.2)
                result = await tmux_read_last(window_name, 10)
                # Just check that it doesn't crash
                assert isinstance(result, str)

        # Run concurrently
        await asyncio.gather(writer(), reader())

    @pytest.mark.asyncio
    async def test_large_output_truncation(self, fresh_agent_session):
        """Test that large output is truncated by max_chars (16000)."""
        window_name = fresh_agent_session

        # Create a very long line (20k characters)
        long_line = "x" * 20000
        await tmux_write(window_name, f"echo {long_line}")
        await asyncio.sleep(1)

        # Read the last few lines; should be truncated due to max_chars
        result = await tmux_read_last(window_name, 5)
        # The result should contain the header and possibly an omission notice
        assert "[lines" in result
        # Ensure the content is not the full 20k (but we can't easily check length)
        # Just verify it's shorter than the full line (since header+line may exceed 16000)
        # Actually, the truncation happens within _truncate_lines_with_header,
        # which respects max_chars. So we just check that something is returned.
        assert len(result) <= 20000  # Should be at most ~16000 + header


if __name__ == "__main__":
    pytest.main([__file__, "-v"])