from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self, overload

from puild.logging import (
    get_default_indent,
    log_action,
    log_indented,
    write_stream_to_file_handlers,
)

_DRY_RUN = False


def set_dry_run(dry_run: bool) -> None:
    """Set global dry-run mode."""
    global _DRY_RUN
    _DRY_RUN = dry_run


def is_dry_run() -> bool:
    """Check if dry-run mode is enabled."""
    return _DRY_RUN


@dataclass
class Result[T: bytes | str]:
    cmd: str
    args: list[str]
    cwd: str
    stdout: T
    stderr: T
    return_code: int

    @property
    def ok(self) -> bool:
        """Return True if command succeeded (return_code == 0)."""
        return self.return_code == 0

    def exit_for_error(self, message: str | None = None) -> None:
        """Exit the process if the command failed with a non-zero exit code."""
        if self.return_code != 0:
            if message:
                log_action("Error", message, "red")
            sys.exit(self.return_code)

    def unwrap(self) -> T:
        """Return stdout if command succeeded, otherwise exit with the return code."""
        self.exit_for_error()
        return self.stdout


class Command:
    def __init__(
        self,
        cmd: str | Path,
        *args: str | Path | Sequence[str | Path],
    ) -> None:
        self._cmd = str(cmd)
        self._args: list[str] = []
        self._env: dict[str, str] = {}
        self._cwd: str = "."
        self._redirect_stdout: Path | None = None
        self._redirect_append: bool = False

        for arg in args:
            if isinstance(arg, (list, tuple)):
                self._args.extend(str(a) for a in arg)
            else:
                self._args.append(str(arg))

    def copy(self) -> Command:
        """Return a shallow copy of the command."""
        cmd = Command(self._cmd, *self._args)
        cmd._env = self._env.copy()
        cmd._cwd = self._cwd
        cmd._redirect_stdout = self._redirect_stdout
        cmd._redirect_append = self._redirect_append
        return cmd

    def arg(self, *args: str | Path) -> Self:
        """Append one or more positional arguments to the command."""
        for a in args:
            self._args.append(str(a))
        return self

    def args(self, args: Iterable[str | Path]) -> Self:
        """Append an iterable of arguments to the command."""
        for a in args:
            self._args.append(str(a))
        return self

    def env(
        self,
        key_or_dict: str | dict[str, str],
        value: str | None = None,
    ) -> Self:
        """Set environment variables for the command."""
        if isinstance(key_or_dict, dict):
            for k, v in key_or_dict.items():
                self._env[str(k)] = str(v)
        elif value is not None:
            self._env[str(key_or_dict)] = str(value)
        return self

    def cwd(self, path: str | Path) -> Self:
        """Set default working directory for this command."""
        self._cwd = str(path)
        return self

    def to_list(self) -> list[str]:
        """Convert command and arguments to a list of strings."""
        return [self._cmd] + self._args

    def __repr__(self) -> str:
        return f"Command({self.to_list()!r})"

    def __or__(self, other: Command | Pipeline) -> Pipeline:
        if isinstance(other, Command):
            return Pipeline([self, other])
        elif isinstance(other, Pipeline):
            return Pipeline([self, *other.commands])
        return NotImplemented

    def __gt__(self, target: str | Path) -> Command:
        """Redirect stdout to file (overwrite): cmd > 'output.txt'"""
        cmd = self.copy()
        cmd._redirect_stdout = Path(target)
        cmd._redirect_append = False
        return cmd

    def __rshift__(self, target: str | Path) -> Command:
        """Redirect stdout to file (append): cmd >> 'output.txt'"""
        cmd = self.copy()
        cmd._redirect_stdout = Path(target)
        cmd._redirect_append = True
        return cmd

    @overload
    def run(
        self,
        *,
        cwd: str | Path | None = None,
        text: Literal[False] = False,
        log: bool = True,
        capture: bool = True,
        stream: bool = False,
        indent: str | None = None,
        env: dict[str, str] | None = None,
        input: bytes | None = None,
        check: bool = False,
        raw: bool = False,
        dry_run: bool | None = None,
    ) -> Result[bytes]: ...

    @overload
    def run(
        self,
        *,
        cwd: str | Path | None = None,
        text: Literal[True],
        log: bool = True,
        capture: bool = True,
        stream: bool = False,
        indent: str | None = None,
        env: dict[str, str] | None = None,
        input: str | None = None,
        check: bool = False,
        raw: bool = False,
        dry_run: bool | None = None,
    ) -> Result[str]: ...

    @overload
    def run(
        self,
        *,
        cwd: str | Path | None = None,
        text: bool = False,
        log: bool = True,
        capture: bool = True,
        stream: bool = False,
        indent: str | None = None,
        env: dict[str, str] | None = None,
        input: Any = None,
        check: bool = False,
        raw: bool = False,
        dry_run: bool | None = None,
    ) -> Result[Any]: ...

    def run(
        self,
        *,
        cwd: str | Path | None = None,
        text: bool = False,
        log: bool = True,
        capture: bool = True,
        stream: bool = False,
        indent: str | None = None,
        env: dict[str, str] | None = None,
        input: Any = None,
        check: bool = False,
        raw: bool = False,
        dry_run: bool | None = None,
    ) -> Result[Any]:
        effective_cwd = str(cwd) if cwd is not None else self._cwd
        is_dry = _DRY_RUN if dry_run is None else dry_run
        effective_indent = get_default_indent() if indent is None else indent

        cmd_display = " ".join(self.to_list())
        if self._redirect_stdout:
            op = ">>" if self._redirect_append else ">"
            cmd_display = f"{cmd_display} {op} {self._redirect_stdout}"

        if log:
            if effective_cwd != ".":
                log_action("CD", effective_cwd, "yellow")
            if is_dry:
                log_action("Dry-Run", cmd_display, "cyan")
            else:
                log_action("Run", cmd_display, "blue")

        empty_out = "" if text else b""
        if is_dry:
            return Result(
                cmd=self._cmd,
                args=self._args,
                cwd=effective_cwd,
                stdout=empty_out,
                stderr=empty_out,
                return_code=0,
            )

        merged_env = os.environ.copy()
        if self._env:
            merged_env.update(self._env)
        if env:
            merged_env.update(env)

        start = time.perf_counter()

        if self._redirect_stdout:
            mode = "a" if self._redirect_append else "w"
            if not text:
                mode += "b"
            parent = self._redirect_stdout.parent
            if parent and not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
            with open(self._redirect_stdout, mode) as f:
                res = subprocess.run(
                    self.to_list(),
                    cwd=effective_cwd,
                    text=text,
                    env=merged_env,
                    input=input,
                    stdout=f,
                    stderr=subprocess.PIPE if capture else None,
                    check=False,
                )
            stdout_res = empty_out
            stderr_res = res.stderr if capture and res.stderr is not None else empty_out
            return_code = res.returncode
        elif raw:
            # Raw interactive TTY execution without interception
            res = subprocess.run(
                self.to_list(),
                cwd=effective_cwd,
                text=text,
                env=merged_env,
                input=input,
                capture_output=False,
                check=False,
            )
            stdout_res = empty_out
            stderr_res = empty_out
            return_code = res.returncode
        elif stream or not capture:
            # Stream output live to terminal with indentation
            stdout_res, stderr_res, return_code = self._run_stream(
                cmd_list=self.to_list(),
                cwd=effective_cwd,
                text=text,
                env=merged_env,
                input_data=input,
                indent=effective_indent,
                collect_output=capture,
            )
        else:
            # Default capture=True, stream=False
            res = subprocess.run(
                self.to_list(),
                cwd=effective_cwd,
                text=text,
                env=merged_env,
                input=input,
                capture_output=True,
                check=False,
            )
            stdout_res = res.stdout
            stderr_res = res.stderr
            return_code = res.returncode

        elapsed = time.perf_counter() - start

        if log:
            if return_code != 0:
                if stream or not capture:
                    log_action(
                        "Failed",
                        f"Command failed with exit code {return_code}",
                        "red",
                    )
                else:
                    err_msg = (
                        stderr_res
                        if isinstance(stderr_res, str)
                        else stderr_res.decode("utf-8", errors="replace")
                    )
                    log_action(
                        "Failed",
                        f"Command failed with exit code {return_code}",
                        "red",
                    )
                    if err_msg.strip():
                        log_indented(err_msg.strip(), indent=effective_indent)
            else:
                log_action("Success", f"Took {elapsed:.3f}s", "green")

        result = Result(
            cmd=self._cmd,
            args=self._args,
            cwd=effective_cwd,
            stdout=stdout_res,
            stderr=stderr_res,
            return_code=return_code,
        )

        if check:
            result.exit_for_error()

        return result

    def _run_stream(
        self,
        cmd_list: list[str],
        cwd: str,
        text: bool,
        env: dict[str, str],
        input_data: Any,
        indent: str,
        collect_output: bool = True,
    ) -> tuple[Any, Any, int]:
        stdin_setting = subprocess.PIPE if input_data is not None else None
        proc = subprocess.Popen(
            cmd_list,
            cwd=cwd,
            text=text,
            env=env,
            stdin=stdin_setting,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if input_data is not None and proc.stdin:
            if (text and isinstance(input_data, str)) or (
                not text and isinstance(input_data, bytes)
            ):
                proc.stdin.write(input_data)
            proc.stdin.close()

        stdout_chunks: list[Any] = []
        stderr_chunks: list[Any] = []

        def reader(pipe, chunks, dest_stream):
            if pipe is None:
                return
            try:
                if text:
                    for line in iter(pipe.readline, ""):
                        if collect_output:
                            chunks.append(line)
                        if not line.strip():
                            dest_stream.write(line)
                            write_stream_to_file_handlers(line)
                        else:
                            formatted = f"{indent}{line}"
                            dest_stream.write(formatted)
                            write_stream_to_file_handlers(formatted)
                        dest_stream.flush()
                else:
                    target = getattr(dest_stream, "buffer", dest_stream)
                    indent_bytes = indent.encode("utf-8")
                    for line in iter(pipe.readline, b""):
                        if collect_output:
                            chunks.append(line)
                        if not line.strip():
                            target.write(line)
                            write_stream_to_file_handlers(line.decode("utf-8", errors="replace"))
                        else:
                            formatted_bytes = indent_bytes + line
                            target.write(formatted_bytes)
                            write_stream_to_file_handlers(formatted_bytes.decode("utf-8", errors="replace"))
                        target.flush()
            finally:
                pipe.close()

        t_out = threading.Thread(
            target=reader, args=(proc.stdout, stdout_chunks, sys.stdout)
        )
        t_err = threading.Thread(
            target=reader, args=(proc.stderr, stderr_chunks, sys.stderr)
        )
        t_out.start()
        t_err.start()

        proc.wait()
        t_out.join()
        t_err.join()

        empty = "" if text else b""
        out_res = (
            ("".join(stdout_chunks) if text else b"".join(stdout_chunks))
            if collect_output
            else empty
        )
        err_res = (
            ("".join(stderr_chunks) if text else b"".join(stderr_chunks))
            if collect_output
            else empty
        )

        return out_res, err_res, proc.returncode


class Pipeline:
    def __init__(self, commands: list[Command]) -> None:
        self.commands: list[Command] = commands

    def __or__(self, other: Command | Pipeline) -> Pipeline:
        if isinstance(other, Command):
            return Pipeline([*self.commands, other])
        elif isinstance(other, Pipeline):
            return Pipeline([*self.commands, *other.commands])
        return NotImplemented

    def __repr__(self) -> str:
        return f"Pipeline({self.commands!r})"

    def run(
        self,
        *,
        cwd: str | Path = ".",
        text: bool = True,
        log: bool = True,
        stream: bool = False,
        indent: str | None = None,
        input: str | bytes | None = None,
        check: bool = False,
        dry_run: bool | None = None,
    ) -> Result[Any]:
        is_dry = _DRY_RUN if dry_run is None else dry_run
        cmd_display = " | ".join(" ".join(c.to_list()) for c in self.commands)
        effective_cwd = str(cwd)
        effective_indent = get_default_indent() if indent is None else indent

        if log:
            if effective_cwd != ".":
                log_action("CD", effective_cwd, "yellow")
            if is_dry:
                log_action("Dry-Run", cmd_display, "cyan")
            else:
                log_action("Run", cmd_display, "blue")

        empty_out = "" if text else b""
        if is_dry or not self.commands:
            return Result(
                cmd=cmd_display,
                args=[],
                cwd=effective_cwd,
                stdout=empty_out,
                stderr=empty_out,
                return_code=0,
            )

        start = time.perf_counter()
        processes: list[subprocess.Popen] = []

        for i, cmd in enumerate(self.commands):
            is_first = i == 0

            if is_first:
                stdin = subprocess.PIPE if input is not None else None
            else:
                stdin = processes[-1].stdout

            stdout = subprocess.PIPE

            merged_env = os.environ.copy()
            if cmd._env:
                merged_env.update(cmd._env)

            proc = subprocess.Popen(
                cmd.to_list(),
                cwd=effective_cwd,
                stdin=stdin,
                stdout=stdout,
                stderr=subprocess.PIPE,
                text=text,
                env=merged_env,
            )

            if not is_first and processes[-1].stdout:
                processes[-1].stdout.close()

            processes.append(proc)

        last_proc = processes[-1]

        if stream:
            stdout_chunks: list[Any] = []
            stderr_chunks: list[Any] = []

            def reader(pipe, chunks, dest_stream):
                if pipe is None:
                    return
                try:
                    if text:
                        for line in iter(pipe.readline, ""):
                            chunks.append(line)
                            if not line.strip():
                                dest_stream.write(line)
                                write_stream_to_file_handlers(line)
                            else:
                                formatted = f"{effective_indent}{line}"
                                dest_stream.write(formatted)
                                write_stream_to_file_handlers(formatted)
                            dest_stream.flush()
                    else:
                        target = getattr(dest_stream, "buffer", dest_stream)
                        indent_bytes = effective_indent.encode("utf-8")
                        for line in iter(pipe.readline, b""):
                            chunks.append(line)
                            if not line.strip():
                                target.write(line)
                                write_stream_to_file_handlers(line.decode("utf-8", errors="replace"))
                            else:
                                formatted_bytes = indent_bytes + line
                                target.write(formatted_bytes)
                                write_stream_to_file_handlers(formatted_bytes.decode("utf-8", errors="replace"))
                            target.flush()
                finally:
                    pipe.close()

            t_out = threading.Thread(
                target=reader, args=(last_proc.stdout, stdout_chunks, sys.stdout)
            )
            t_err = threading.Thread(
                target=reader, args=(last_proc.stderr, stderr_chunks, sys.stderr)
            )
            t_out.start()
            t_err.start()

            if input is not None and processes[0].stdin:
                try:
                    if (text and isinstance(input, str)) or (
                        not text and isinstance(input, bytes)
                    ):
                        processes[0].stdin.write(input)
                    processes[0].stdin.close()
                except BrokenPipeError:
                    pass

            last_proc.wait()
            t_out.join()
            t_err.join()

            stdout_res = "".join(stdout_chunks) if text else b"".join(stdout_chunks)
            stderr_res = "".join(stderr_chunks) if text else b"".join(stderr_chunks)
        else:
            if input is not None and processes[0].stdin:
                stdout_res, stderr_res = last_proc.communicate(
                    input=input if len(processes) == 1 else None
                )
                if len(processes) > 1 and processes[0].stdin:
                    try:
                        if (text and isinstance(input, str)) or (
                            not text and isinstance(input, bytes)
                        ):
                            processes[0].stdin.write(input)
                        processes[0].stdin.close()
                    except BrokenPipeError:
                        pass
                    stdout_res, stderr_res = last_proc.communicate()
            else:
                stdout_res, stderr_res = last_proc.communicate()

        for p in processes[:-1]:
            if p.stderr:
                p.stderr.close()
            p.wait()

        elapsed = time.perf_counter() - start
        return_code = last_proc.returncode

        if log:
            if return_code != 0:
                if stream:
                    log_action(
                        "Failed",
                        f"Command failed with exit code {return_code}",
                        "red",
                    )
                else:
                    err_msg = (
                        stderr_res
                        if isinstance(stderr_res, str)
                        else stderr_res.decode("utf-8", errors="replace")
                    )
                    log_action(
                        "Failed",
                        f"Command failed with exit code {return_code}",
                        "red",
                    )
                    if err_msg.strip():
                        log_indented(err_msg.strip(), indent=effective_indent)
            else:
                log_action("Success", f"Took {elapsed:.3f}s", "green")

        result = Result(
            cmd=cmd_display,
            args=[],
            cwd=effective_cwd,
            stdout=stdout_res,
            stderr=stderr_res,
            return_code=return_code,
        )

        if check:
            result.exit_for_error()

        return result
