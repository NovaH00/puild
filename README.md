# puild

A lightweight, modern build tool and command runner for Python.

## Features

- **Command Runner:** Run system commands with fluent argument construction, rich logging, and typed results.
- **Pipelines & Redirection:** Shell-like piping (`cmd1 | cmd2`) and redirection (`cmd > "file.txt"`).
- **Streaming & Live Output:** Real-time stdout/stderr streaming while capturing output into typed [`Result`](src/puild/command.py) objects.
- **Dry-run & Quiet Modes:** Preview commands before execution or silence logs during scripts and testing.
- **Build Primitives:** Timestamp-based rebuild detection (`needs_rebuild`) and filesystem helpers (`mkdir`, `rm`, `copy`, `find_files`).

## Quickstart

### 1. Basic Command Execution

```python
from puild import Command

# Direct instantiation
cmd = Command("gcc", "-Wall", "-O2", "main.c", "-o", "bin/app")
res = cmd.run(text=True)

if not res.ok:
    res.exit_for_error()
```

### 2. Fluent Argument Builder & Environment

```python
from puild import Command

cmd = (
    Command("gcc")
    .arg("-Wall")
    .arg("-O2")
    .args(["main.c", "-o", "bin/app"])
    .env("CFLAGS", "-march=native")
    .cwd("src")
)

res = cmd.run(text=True)
print(res.stdout)
```

### 3. Piping and File Redirection

```python
from puild import Command

# Pipe between commands
pipe = Command("cat", "access.log") | Command("grep", "ERROR")
res = pipe.run(text=True)

# File redirection
cmd = Command("echo", "build completed") > "build.log"
cmd.run()

# Append to file
cmd = Command("echo", "second step completed") >> "build.log"
cmd.run()
```

### 4. Live Streaming Output & Indentation

Stream command output to stdout/stderr in real-time. Output is automatically indented (default 4 spaces) so it stays visually separated from puild's action logs:

```python
from puild import Command, set_default_indent

# Stream with default 4-space indentation
cmd = Command("npm", "install")
cmd.run(stream=True, text=True)

# Custom indentation per-command or globally
cmd.run(stream=True, indent="  ")  # 2 spaces
set_default_indent("    ")        # Set global default
```

### 5. Incremental Builds (`needs_rebuild`)

Skip compiling when targets are already up-to-date:

```python
from puild import Command, needs_rebuild, find_files

sources = find_files("src", "*.c")
target = "build/app"

if needs_rebuild(target, sources, log=True):
    Command("gcc", *sources, "-o", target).run(check=True)
```

### 6. Filesystem Helpers

```python
from puild import mkdir, rm, copy, find_files

# Create directories
mkdir("build/bin")

# Find files
c_files = find_files("src", "*.c", recursive=True)

# Copy files or directories
copy("src/config.json", "build/config.json")

# Remove files or directories
rm("build", recursive=True)
```

### 7. Logging & File Routing

`puild` uses Python's standard `logging` library (`logging.getLogger("puild")`). You can route logs to a file, rotate files, or customize levels:

```python
from puild import Command, configure_logging

# Route logs to both console and a log file
configure_logging(log_file="build.log")

# Or log strictly to a file without console output
configure_logging(log_file="build.log", console=False)

# Or with log rotation
configure_logging(log_file="build.log", max_bytes=10_000_000, backup_count=3)
```

You can also attach standard Python `logging` handlers directly:

```python
import logging

handler = logging.FileHandler("custom.log")
logging.getLogger("puild").addHandler(handler)
```
