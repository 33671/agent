"""
Tmux interaction tools for managing persistent terminal sessions.

All operations happen in agent_session with one pane per window (always %0).
Uses pyte to emulate the terminal and produce clean, formatted output.
"""

import asyncio
import os
import re
import shlex
import time
from typing import Optional

import pyte
import pyte.screens
import pyte.streams

# Global agent session name - all operations happen in this session
AGENT_SESSION = "agent_session"

# Global per-window storage: (screen, stream, last_file_position)
_window_screens: dict[str, tuple[pyte.Screen, pyte.ByteStream, int]] = {}


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
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return _CmdResult(
            proc.returncode,
            stdout.decode(errors="replace") if stdout else "",
            stderr.decode(errors="replace") if stderr else "",
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


def _get_log_file(window_name: str) -> str:
    """Return the log file path for a given window."""
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", window_name)
    return os.path.join("./", f"agent_session_{safe_name}.log")


def _truncate_content(content: str, max_chars: int) -> str:
    """Truncate content to max_chars, adding an ellipsis if needed."""
    if len(content) <= max_chars:
        return content
    ellipsis = "\n... (truncated)\n"
    available = max_chars - len(ellipsis)
    if available <= 0:
        return ellipsis
    truncated = content[:available]
    return truncated + ellipsis


async def _get_pane_size(window_name: str) -> tuple[int, int]:
    """Return (width, height) of the pane for the given window."""
    pane_target = _get_pane_target(window_name)
    result = await _tmux(
        "display", "-t", pane_target, "-p", "#{pane_width} #{pane_height}"
    )
    if result.returncode != 0:
        return (1000, 24)  # fallback
    parts = result.stdout.strip().split()
    if len(parts) >= 2:
        try:
            width = int(parts[0])
            height = int(parts[1])
            return (width, height)
        except ValueError:
            pass
    return (1000, 24)


async def _ensure_screen(window_name: str) -> tuple[pyte.Screen, pyte.ByteStream]:
    """Create screen+stream for the window if not already present."""
    if window_name not in _window_screens:
        width, height = await _get_pane_size(window_name)
        screen = pyte.Screen(width, height)
        stream = pyte.ByteStream(screen)
        _window_screens[window_name] = (screen, stream, 0)
    return _window_screens[window_name][:2]


async def _update_screen_size(window_name: str):
    """Resize the screen if the actual pane dimensions changed."""
    if window_name not in _window_screens:
        return
    screen, _, _ = _window_screens[window_name]
    width, height = await _get_pane_size(window_name)
    if screen.columns != width or screen.lines != height:
        screen.resize(height, width)  # resize takes (lines, columns)


async def _feed_new_data(window_name: str):
    """Read new bytes from the log file and feed them to the screen."""
    if window_name not in _window_screens:
        return
    screen, stream, last_pos = _window_screens[window_name]
    log_file = _get_log_file(window_name)
    if not os.path.exists(log_file):
        return
    try:
        with open(log_file, "rb") as f:
            f.seek(last_pos)
            new_bytes = f.read()
            if new_bytes:
                stream.feed(new_bytes)
                _window_screens[window_name] = (screen, stream, f.tell())
    except Exception:
        # If reading fails, leave state unchanged
        pass
    await _update_screen_size(window_name)


async def tmux_new(
    window_name: Optional[str] = None,
    start_directory: Optional[str] = None,
    longrunning_command: Optional[str] = None,
) -> str:
    """Create a new tmux window in the agent session with one pane."""
    if not await _session_exists():
        create_args = ["new-session", "-s", AGENT_SESSION, "-d"]
        if window_name:
            create_args += ["-n", window_name]
        if start_directory:
            create_args += ["-c", start_directory]
        else:
            create_args += ["-c", os.getcwd()]
        create_args += ["-x", "1000", "-y", "1000"]
        if longrunning_command:
            create_args += ["--"] + shlex.split(longrunning_command)
        else:
            create_args += ["--"] + ["bash"]

        result = await _tmux(*create_args)
        if result.returncode != 0:
            return f"Error: Failed to create tmux session: {result.stderr}"

        actual_window = window_name if window_name else "0"
    else:
        args = ["new-window", "-t", AGENT_SESSION, "-d"]
        if window_name:
            if await _window_exists(window_name):
                return f"Error: Window '{window_name}' already exists"
            args += ["-n", window_name]
        else:
            args += ["-F", "#{window_name}"]  # Request output of new window name
        if start_directory:
            args += ["-c", start_directory]
        else:
            args += ["-c", os.getcwd()]
        if longrunning_command:
            args += ["--"] + shlex.split(longrunning_command)
        else:
            args += ["--"] + ["bash"]

        result = await _tmux(*args)
        if result.returncode != 0:
            return f"Error: Failed to create tmux window: {result.stderr}"

        if window_name:
            actual_window = window_name
        else:
            actual_window = result.stdout.strip()
            if not actual_window:
                cur_result = await _tmux(
                    "display-message", "-t", AGENT_SESSION, "-p", "#{window_name}"
                )
                actual_window = (
                    cur_result.stdout.strip() if cur_result.returncode == 0 else "0"
                )

    # Set up pipe-pane to capture stdout+stderr into a log file
    pane_target = _get_pane_target(actual_window)
    log_file = _get_log_file(actual_window)

    if os.path.exists(log_file):
        os.remove(log_file)

    pipe_result = await _tmux("pipe-pane", "-t", pane_target, f"cat >> {log_file}")
    if pipe_result.returncode != 0:
        return (
            f"Created window: {pane_target} but pipe-pane failed: {pipe_result.stderr}. "
            f"Reading functions will not work."
        )

    return f"Created window: {pane_target}"


async def tmux_read_last(target_window: str, n_lines: int) -> str:
    """Read the last N screen lines from a tmux window (clean, no ANSI codes)."""
    max_chars: int = 16000
    if not await _window_exists(target_window):
        return f"Error: Window '{target_window}' does not exist"

    await _ensure_screen(target_window)
    await _feed_new_data(target_window)
    screen, _, _ = _window_screens[target_window]

    # Clean the right-side padding from every line
    lines = [line.rstrip() for line in screen.display]

    # --- FIX: Strip trailing empty lines from the bottom of the terminal ---
    # This prevents n_lines from grabbing completely blank lines
    # if the text hasn't scrolled all the way down to the bottom.
    while lines and not lines[-1]:
        lines.pop()

    selected = lines[-n_lines:] if n_lines > 0 else lines

    # Join and strip any trailing empty newlines
    content = "\n".join(selected).rstrip()

    if max_chars > 0 and len(content) > max_chars:
        content = _truncate_content(content, max_chars)
    return content


async def tmux_write(target_window: str, input: str, wait_secs: float = 1.0) -> str:
    """Send input to a window's pane and return the output after waiting."""
    if not await _window_exists(target_window):
        return f"Error: Window '{target_window}' does not exist"

    pane_target = _get_pane_target(target_window)

    # 1. Catch up the main screen and record the file byte position BEFORE sending
    await _ensure_screen(target_window)
    await _feed_new_data(target_window)
    _, _, pos_before = _window_screens[target_window]

    # 2. Check for trailing newline (both literal \n and escaped \\n)
    send_enter = True
    if input.endswith("\n"):
        input = input[:-1]
    elif input.endswith("\\n"):
        send_enter = True
        input = input[:-2]

    # 3. Check for trailing control sequences (e.g., C-c, M-x, Escape, Tab)
    trailing_key = None
    ctrl_match = re.search(r"([MC]-.|Enter|Escape|Tab|Space)$", input)
    if ctrl_match:
        trailing_key = ctrl_match.group(1)
        # Strip the control key from the input
        input = input[: ctrl_match.start()]

    # 4. Send the remaining literal string safely
    if input:
        await _tmux("send-keys", "-t", pane_target, "-l", input)

    # 5. Send the extracted control key (if any)
    if trailing_key:
        await _tmux("send-keys", "-t", pane_target, trailing_key)

    # 6. Send Enter if the input originally ended with a newline
    if send_enter:
        await _tmux("send-keys", "-t", pane_target, "Enter")

    # 7. Wait for the specified duration for the command to execute
    await asyncio.sleep(wait_secs)

    # 8. Catch up the main screen and get the new byte position AFTER waiting
    await _feed_new_data(target_window)
    _, _, pos_after = _window_screens[target_window]

    # 9. Extract only the newly generated raw bytes from the log
    log_file = _get_log_file(target_window)
    new_bytes = b""
    if os.path.exists(log_file) and pos_after > pos_before:
        try:
            with open(
                log_file, "rb"
            ) as f:  # Removed encoding="utf-8" since we read 'rb'
                f.seek(pos_before)
                new_bytes = f.read(pos_after - pos_before)
        except Exception as e:
            return f"Input sent, but failed to read new output: {e}"

    # 10. Parse the new bytes through a dynamically tall temporary screen to strip ANSI
    output = ""
    if new_bytes:
        width, _ = await _get_pane_size(target_window)
        # Estimate needed lines to prevent truncation
        estimated_lines = max(100, new_bytes.count(b"\n") + 50)

        temp_screen = pyte.Screen(width, estimated_lines)
        temp_stream = pyte.ByteStream(temp_screen)
        temp_stream.feed(new_bytes)

        # Extract display, right-strip trailing spaces PER LINE, and remove empty trailing lines
        cleaned_lines = [line.rstrip() for line in temp_screen.display]
        while cleaned_lines and not cleaned_lines[-1]:
            cleaned_lines.pop()

        output = "\n".join(cleaned_lines).strip()

    max_chars = 16000
    if output:
        if len(output) > max_chars:
            output = _truncate_content(output, max_chars)
        return f"Input sent to {target_window}. Output after {wait_secs}s:\n{output}"
    else:
        return f"Input sent to {target_window}. No new output after {wait_secs}s."


async def tmux_del(target_window: str) -> str:
    """Kill a window in agent_session and clean up its pipe-pane log."""
    if not await _window_exists(target_window):
        return f"Error: Window '{target_window}' does not exist"

    # Stop pipe-pane
    pane_target = _get_pane_target(target_window)
    await _tmux("pipe-pane", "-t", pane_target)

    # Remove log file
    log_file = _get_log_file(target_window)
    if os.path.exists(log_file):
        os.remove(log_file)

    # Remove from pyte state
    if target_window in _window_screens:
        del _window_screens[target_window]

    # Kill the window
    window_target = f"{AGENT_SESSION}:{target_window}"
    result = await _tmux("kill-window", "-t", window_target)
    if result.returncode != 0:
        return f"Error: Could not delete window '{target_window}': {result.stderr}"

    return f"Killed window: {target_window}"


# async def tmux_del(target_window: str) -> str:
#     """Kill a window in agent_session and clean up its pipe-pane log."""
#     if not await _window_exists(target_window):
#         return f"Error: Window '{target_window}' does not exist"

#     return f"We are in debug mode, so window: {target_window} is not real killed"


async def tmux_list() -> str:
    """List all windows in agent_session."""
    if not await _session_exists():
        return "No active windows"

    result = await _tmux("list-windows", "-t", AGENT_SESSION)
    if result.returncode != 0:
        return "No active windows found or error occurred"

    windows = [line.strip() for line in result.stdout.strip().split("\n") if line]
    return "\n".join(windows) if windows else "No active windows found"


async def tmux_wait(
    target_window: str, text: str, timeout: Optional[float] = None
) -> str:
    """Wait for a substring to appear in the window's rendered screen content."""
    if not await _window_exists(target_window):
        return f"Error: Window '{target_window}' does not exist"

    await _ensure_screen(target_window)
    start_time = time.time()

    while True:
        await _feed_new_data(target_window)
        screen, _, _ = _window_screens[target_window]
        full_text = "\n".join(screen.display)

        if text in full_text:
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
                    "kill",
                    "-s",
                    signal,
                    pid,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await kill_proc.wait()
                if kill_proc.returncode == 0:
                    return f"Signal {signal} sent to process {pid} in {target_window}"

        return f"Error: Unsupported signal or cannot send: {signal}"


# Export all tmux tools
TMUX_TOOLS = {
    "tmux_new": tmux_new,
    "tmux_read_last": tmux_read_last,
    "tmux_write": tmux_write,
    "tmux_del": tmux_del,
    "tmux_list": tmux_list,
    "tmux_wait": tmux_wait,
    "tmux_send_signal": tmux_send_signal,
}
