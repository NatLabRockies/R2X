"""I/O helpers for reading and writing power system data."""

import sys
import tempfile
from pathlib import Path
from typing import IO

from r2x_core import Err, Ok, Result, System


def from_stdin() -> Result[System, str]:
    """Read System from stdin as JSON.

    Returns
    -------
    Result[System, str]
        Ok with loaded System or Err with error message

    Examples
    --------
    >>> # cat system.json | python script.py
    >>> result = from_stdin()
    >>> if result.is_ok():
    ...     system = result.unwrap()
    """
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as tmp:
            tmp.write(sys.stdin.buffer.read())
            tmp_path = Path(tmp.name)

        system = System.from_json(tmp_path, auto_add_composed_components=True)
        tmp_path.unlink()
        return Ok(system)
    except Exception as e:
        return Err(f"Failed to read from stdin: {e}")


def to_stdout(system: System) -> Result[None, str]:
    """Write System to stdout as JSON.

    Parameters
    ----------
    system : System
        System to write

    Returns
    -------
    Result[None, str]
        Ok(None) on success or Err with error message

    Examples
    --------
    >>> result = to_stdout(system)
    >>> if result.is_err():
    ...     print(f"Failed: {result.unwrap_err()}")
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "system.json"
            system.to_json(tmp_path, overwrite=True)

            with open(tmp_path, "rb") as f:
                sys.stdout.buffer.write(f.read())

        return Ok(None)
    except Exception as e:
        return Err(f"Failed to write to stdout: {e}")


def from_file(path: str | Path) -> Result[System, str]:
    """Read System from JSON file.

    Parameters
    ----------
    path : str | Path
        Path to JSON file

    Returns
    -------
    Result[System, str]
        Ok with loaded System or Err with error message

    Examples
    --------
    >>> result = from_file("system.json")
    >>> if result.is_ok():
    ...     system = result.unwrap()
    """
    try:
        system = System.from_json(path, auto_add_composed_components=True)
        return Ok(system)
    except Exception as e:
        return Err(f"Failed to read from {path}: {e}")


def to_file(system: System, path: str | Path) -> Result[None, str]:
    """Write System to JSON file.

    Parameters
    ----------
    system : System
        System to write
    path : str | Path
        Output file path

    Returns
    -------
    Result[None, str]
        Ok(None) on success or Err with error message

    Examples
    --------
    >>> result = to_file(system, "output.json")
    >>> if result.is_err():
    ...     print(f"Failed: {result.unwrap_err()}")
    """
    try:
        system.to_json(path, overwrite=True)
        return Ok(None)
    except Exception as e:
        return Err(f"Failed to write to {path}: {e}")


def from_bytes(data: bytes) -> Result[System, str]:
    """Read System from JSON bytes.

    Parameters
    ----------
    data : bytes
        JSON data as bytes

    Returns
    -------
    Result[System, str]
        Ok with loaded System or Err with error message

    Examples
    --------
    >>> with open("system.json", "rb") as f:
    ...     data = f.read()
    >>> result = from_bytes(data)
    """
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        system = System.from_json(tmp_path, auto_add_composed_components=True)
        tmp_path.unlink()
        return Ok(system)
    except Exception as e:
        return Err(f"Failed to read from bytes: {e}")


def to_bytes(system: System) -> Result[bytes, str]:
    """Convert System to JSON bytes.

    Parameters
    ----------
    system : System
        System to convert

    Returns
    -------
    Result[bytes, str]
        Ok with JSON bytes or Err with error message

    Examples
    --------
    >>> result = to_bytes(system)
    >>> if result.is_ok():
    ...     data = result.unwrap()
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "system.json"
            system.to_json(tmp_path, overwrite=True)

            with open(tmp_path, "rb") as f:
                data = f.read()

        return Ok(data)
    except Exception as e:
        return Err(f"Failed to convert to bytes: {e}")


def from_stream(stream: IO[bytes]) -> Result[System, str]:
    """Read System from binary stream.

    Parameters
    ----------
    stream : IO[bytes]
        Binary stream to read from

    Returns
    -------
    Result[System, str]
        Ok with loaded System or Err with error message
    """
    try:
        data = stream.read()
        return from_bytes(data)
    except Exception as e:
        return Err(f"Failed to read from stream: {e}")


def to_stream(system: System, stream: IO[bytes]) -> Result[None, str]:
    """Write System to binary stream.

    Parameters
    ----------
    system : System
        System to write
    stream : IO[bytes]
        Binary stream to write to

    Returns
    -------
    Result[None, str]
        Ok(None) on success or Err with error message
    """
    try:
        bytes_result = to_bytes(system)
        if bytes_result.is_err():
            err_msg: str = bytes_result.err() or "Unknown error"
            return Err(err_msg)

        data = bytes_result.unwrap()
        stream.write(data)
        return Ok(None)
    except Exception as e:
        return Err(f"Failed to write to stream: {e}")
