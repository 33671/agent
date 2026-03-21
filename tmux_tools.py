"""
Tmux interaction tools for managing persistent terminal sessions.

All operations happen in agent_session with one pane per window (always %0).
"""

import asyncio
import hashlib
import json
import os
import re
import shlex
import time
from typing import Optional

# Global agent session name - all operations happen in this session
AGENT_SESSION = "agent_session"

# Global dictionary to track read content hashes per window
# This allows tmux_read/tmux_read_last and tmux_wait to share state
_window_read_hashes: dict[str, set[str]] = {}


class _CmdResult:
    """Helper class to mimic subprocess.CompletedProcess for async execution."""
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


async def _tmux(*args: str, capture_output=True) -> _CmdResult:
    """Run a tmux command asynchronously and return _CmdResult."""
    cmd = ["tmux"] + list(args)
    if capture_output:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return _CmdResult(
            proc.returncode,
            stdout.decode(errors='replace') if stdout else "",
            stderr.decode(errors='replace') if stderr else ""
        )
    else:
        proc = await asyncio.create_subprocess_exec(*cmd)
        await proc.wait()
        return _CmdResult(proc.returncode, "", "")


async def _session_exists() -> bool:
    """Check if agent session exists."""
    result = await _tmux("has-session", "-t", AGENT_SESSION)
    return result.returncode == 0


async def _window_exists(window_name: str) -> bool:
    """Check if a window exists in agent session."""
    result = await _tmux("list-windows", "-t", AGENT_SESSION, "-F", "#{window_name}")
    if result.returncode != 0:
        return False
    windows = [line.strip() for line in result.stdout.split("\n") if line.strip()]
    return window_name in windows


def _get_pane_target(window_name: str) -> str:
    """Get the full pane target for a window (window.0)."""
    return f"{AGENT_SESSION}:{window_name}.0"


async def _get_pane_lines(pane_target: str) -> list[str]:
    """Helper to get actual populated lines without tmux screen padding."""
    # Use '-S -' to reliably get the full history 
    result = await _tmux("capture-pane", "-t", pane_target, "-p", "-S", "-")
    if result.returncode != 0:
        raise RuntimeError(f"Failed to read pane: {result.stderr}")

    lines = result.stdout.splitlines(keepends=True)
    
    # Strip terminal padding (trailing empty lines added by tmux bounding box)
    non_empty_end = 0
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip('\r\n\t '):
            non_empty_end = i + 1
            break
            
    return lines[:non_empty_end] if non_empty_end > 0 else []


async def tmux_new(
    window_name: Optional[str] = None,
    start_directory: Optional[str] = None,
    command: Optional[str] = None,
) -> str:
    """Create a new tmux window in the agent session with one pane."""
    if not await _session_exists():
        create_args = ["new-session", "-s", AGENT_SESSION, "-d"]
        if window_name:
            create_args += ["-n", window_name]
        if start_directory:
            create_args += ["-c", start_directory]
        if command:
            create_args += ["--"] + shlex.split(command)

        result = await _tmux(*create_args)
        if result.returncode != 0:
            return f"Error: Failed to create tmux session: {result.stderr}"

        actual_window = window_name if window_name else "0"
        return f"Created window: {AGENT_SESSION}:{actual_window}.0"

    args = ["new-window", "-t", AGENT_SESSION, "-d"]
    if window_name:
        if await _window_exists(window_name):
            return f"Error: Window '{window_name}' already exists"
        args += ["-n", window_name]
    if start_directory:
        args += ["-c", start_directory]
    if command:
        args += ["--"] + shlex.split(command)

    result = await _tmux(*args)
    if result.returncode != 0:
        return f"Error: Failed to create tmux window: {result.stderr}"

    if window_name:
        target = _get_pane_target(window_name)
    else:
        list_result = await _tmux("list-windows", "-t", AGENT_SESSION, "-F", "#{window_name}")
        if list_result.returncode == 0:
            windows = [l.strip() for l in list_result.stdout.strip().split("\n") if l.strip()]
            last_window = windows[-1] if windows else "0"
            target = _get_pane_target(last_window)
        else:
            target = f"{AGENT_SESSION}:0.0"

    return f"Created window: {target}"


def _get_window_hashes(window_name: str) -> set[str]:
    """Get the set of read content hashes for a window."""
    return _window_read_hashes.get(window_name, set())


def _mark_lines_as_read(window_name: str, lines: list[str]) -> None:
    """Mark lines as read for a window."""
    if window_name not in _window_read_hashes:
        _window_read_hashes[window_name] = set()
    for line in lines:
        line_hash = hashlib.md5(line.encode()).hexdigest()
        _window_read_hashes[window_name].add(line_hash)


def _truncate_lines_with_header(
    lines: list[str], max_chars: int, start_line: int, end_line: int
) -> str:
    """Truncate lines to fit within max_chars, dynamically updating omission count."""
    header = f"[lines {start_line}-{end_line}]\n"
    available_chars = max_chars - len(header)
    
    if available_chars <= 0:
        return header
        
    total_chars = sum(len(line) for line in lines)
    if total_chars <= available_chars:
        return header + "".join(lines)
        
    ellipsis_template = "... ({omitted} lines omitted)\n"
    selected = []
    current_chars = 0
    
    for line in reversed(lines):
        omitted_count = len(lines) - (len(selected) + 1)
        ellipsis = ellipsis_template.format(omitted=omitted_count) if omitted_count > 0 else ""
        
        test_length = current_chars + len(line) + len(ellipsis)
        
        if test_length <= available_chars:
            selected.append(line)
            current_chars += len(line)
        else:
            break
            
    selected.reverse()
    omitted = len(lines) - len(selected)
    
    if omitted == 0:
        return header + "".join(lines)
    elif len(selected) == 0:
        return header + ellipsis_template.format(omitted=len(lines))
    else:
        return header + ellipsis_template.format(omitted=omitted) + "".join(selected)


async def tmux_read_last(target_window: str, n_lines: int) -> str:
    """Read the last N lines from a tmux window."""
    max_chars: int = 16000
    if not await _window_exists(target_window):
        return f"Error: Window '{target_window}' does not exist"

    pane_target = _get_pane_target(target_window)
    try:
        lines = await _get_pane_lines(pane_target)
    except RuntimeError as e:
        return str(e)

    actual_lines = len(lines)
    start = max(0, actual_lines - n_lines)
    selected_lines = lines[start:]
    
    start_line = start + 1
    end_line = actual_lines

    if not selected_lines:
        return f"[lines {start_line}-{end_line}]\n"

    if max_chars > 0:
        content = _truncate_lines_with_header(selected_lines, max_chars, start_line, end_line)
    else:
        content = f"[lines {start_line}-{end_line}]\n" + "".join(selected_lines)

    _mark_lines_as_read(target_window, selected_lines)
    return content


async def tmux_read(target_window: str, line_offset: int, n_lines: int) -> str:
    """Read N lines from a starting offset in a tmux window."""
    max_chars: int = 16000
    if not await _window_exists(target_window):
        return f"Error: Window '{target_window}' does not exist"

    pane_target = _get_pane_target(target_window)
    try:
        lines = await _get_pane_lines(pane_target)
    except RuntimeError as e:
        return str(e)

    total_lines = len(lines)
    if line_offset > total_lines:
        return f"[lines {line_offset}-{line_offset}]\n"

    start = max(0, line_offset - 1)
    end = min(start + n_lines, total_lines)
    selected_lines = lines[start:end]
    
    start_line = start + 1
    end_line = end

    if not selected_lines:
        return f"[lines {start_line}-{end_line}]\n"

    if max_chars > 0:
        content = _truncate_lines_with_header(selected_lines, max_chars, start_line, end_line)
    else:
        content = f"[lines {start_line}-{end_line}]\n" + "".join(selected_lines)

    _mark_lines_as_read(target_window, selected_lines)
    return content


async def tmux_write(target_window: str, input: str) -> str:
    """Send input to a window's pane."""
    if not await _window_exists(target_window):
        return f"Error: Window '{target_window}' does not exist"

    pane_target = _get_pane_target(target_window)
    parts = input.split("\\n")
    
    for i, part in enumerate(parts):
        if part:
            if re.match(r"^[MC]-.$", part) or part in ["Enter", "Escape", "Tab", "Space"]:
                await _tmux("send-keys", "-t", pane_target, part)
            else:
                await _tmux("send-keys", "-t", pane_target, "-l", part)
        
        if i < len(parts) - 1 or (parts and not re.match(r"^[MC]-.$", parts[-1])):
            await _tmux("send-keys", "-t", pane_target, "Enter")

    return f"Input sent to {target_window}"


async def tmux_del(target_window: str) -> str:
    """Kill a window in agent_session."""
    if not await _window_exists(target_window):
        return f"Error: Window '{target_window}' does not exist"

    window_target = f"{AGENT_SESSION}:{target_window}"
    result = await _tmux("kill-window", "-t", window_target)
    if result.returncode != 0:
        return f"Error: Could not delete window '{target_window}': {result.stderr}"
    return f"Killed window: {target_window}"


async def tmux_list() -> str:
    """List all windows in agent_session."""
    if not await _session_exists():
        return "No active windows"

    result = await _tmux("list-windows", "-t", AGENT_SESSION)
    if result.returncode != 0:
        return "No active windows found or error occurred"

    windows = [line.strip() for line in result.stdout.strip().split("\n") if line]
    return "\n".join(windows) if windows else "No active windows found"


async def tmux_wait(target_window: str, text: str, timeout: Optional[float] = None) -> str:
    """Wait for a substring to appear in window output."""
    if not await _window_exists(target_window):
        return f"Error: Window '{target_window}' does not exist"

    start_time = time.time()
    pane_target = _get_pane_target(target_window)
    read_hashes = _get_window_hashes(target_window)

    while True:
        result = await _tmux("capture-pane", "-t", pane_target, "-p", "-S", "-")
        if result.returncode != 0:
            return f"Error: Failed to read pane: {result.stderr}"

        new_content_lines = []
        for line in result.stdout.splitlines(keepends=True):
            line_hash = hashlib.md5(line.encode()).hexdigest()
            if line_hash not in read_hashes:
                new_content_lines.append(line)
                read_hashes.add(line_hash)

        if new_content_lines:
            new_content = "".join(new_content_lines)
            if text in new_content:
                return f"Text '{text}' found in window '{target_window}'"

        if timeout is not None and (time.time() - start_time) >= timeout:
            return f"Timeout: Text '{text}' not found within {timeout} seconds"

        await asyncio.sleep(0.5)


async def tmux_send_signal(target_window: str, signal: str) -> str:
    """Send a signal to the foreground process in a window."""
    if not await _window_exists(target_window):
        return f"Error: Window '{target_window}' does not exist"

    pane_target = _get_pane_target(target_window)
    signal_map = {
        "SIGINT": "C-c",
        "SIGTERM": "C-c",
        "SIGQUIT": "C-\\",
        "SIGSTOP": "C-z",
        "SIGTSTP": "C-z",
    }

    if signal in signal_map:
        await _tmux("send-keys", "-t", pane_target, signal_map[signal])
        return f"Signal {signal} sent to {target_window}"
    else:
        result = await _tmux("display-message", "-t", pane_target, "-p", "#{pane_pid}")
        if result.returncode == 0:
            pid = result.stdout.strip()
            if pid:
                kill_proc = await asyncio.create_subprocess_exec(
                    "kill", "-s", signal, pid,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await kill_proc.wait()
                if kill_proc.returncode == 0:
                    return f"Signal {signal} sent to process {pid} in {target_window}"
                    
        return f"Error: Unsupported signal or cannot send: {signal}"


# Export all tmux tools
TMUX_TOOLS = {
    "tmux_new": tmux_new,
    "tmux_read_last": tmux_read_last,
    "tmux_read": tmux_read,
    "tmux_write": tmux_write,
    "tmux_del": tmux_del,
    "tmux_list": tmux_list,
    "tmux_wait": tmux_wait,
    "tmux_send_signal": tmux_send_signal,
}