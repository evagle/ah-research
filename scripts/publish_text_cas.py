"""Publish a UTF-8 text artifact with compare-and-swap semantics."""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import os
import sys
import tempfile
from pathlib import Path


class PublishError(Exception):
    """Raised when a text artifact cannot be published without data loss."""


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _validate_guards(guards: list[tuple[Path, str]]) -> None:
    for path, expected_sha256 in guards:
        try:
            actual_sha256 = _sha256(path.read_bytes())
        except OSError as exc:
            raise PublishError(f"guard is not readable: {path}: {exc}") from exc
        if actual_sha256 != expected_sha256:
            raise PublishError(f"guard hash mismatch: {path}")


def _exchange_paths(left: Path, right: Path) -> None:
    """Atomically exchange two paths without an overwrite window."""
    libc = ctypes.CDLL(None, use_errno=True)
    left_bytes = os.fsencode(left)
    right_bytes = os.fsencode(right)
    result: int
    if hasattr(libc, "renamex_np"):
        renamex_np = libc.renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(left_bytes, right_bytes, 0x00000002)
    elif hasattr(libc, "renameat2"):
        renameat2 = libc.renameat2
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, left_bytes, -100, right_bytes, 0x00000002)
    else:
        raise PublishError("atomic path exchange is unavailable on this platform")
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def _restore_exchanged_target(
    target: Path,
    displaced_path: Path,
    published_body: bytes,
) -> bool:
    """Restore the displaced target only when no later editor changed it."""
    _exchange_paths(displaced_path, target)
    current_at_displaced = displaced_path.read_bytes()
    if current_at_displaced == published_body:
        return True
    _exchange_paths(displaced_path, target)
    return False


def publish_text(
    source: Path,
    target: Path,
    expected_sha256: str,
    guards: list[tuple[Path, str]] | None = None,
) -> str:
    try:
        body = source.read_bytes()
        body.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PublishError(f"source is not readable UTF-8 text: {exc}") from exc
    if expected_sha256 != "absent" and (
        len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise PublishError("expected SHA-256 must be lowercase hex or absent")

    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f".{target.name}.lock")
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(lock_fd)
        raise PublishError("target is locked by another publisher") from exc
    except OSError as exc:
        raise PublishError(f"cannot open target lock: {exc}") from exc

    temporary: Path | None = None
    try:
        _validate_guards(guards or [])
        original_body: bytes | None = None
        if target.exists():
            original_body = target.read_bytes()
            actual_sha256 = _sha256(original_body)
            if expected_sha256 == "absent" or actual_sha256 != expected_sha256:
                raise PublishError(
                    "baseline hash mismatch; refusing to overwrite concurrent update"
                )
        elif expected_sha256 != "absent":
            raise PublishError("baseline hash mismatch; target disappeared before publication")

        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".partial",
            delete=False,
        ) as sink:
            sink.write(body)
            sink.flush()
            os.fsync(sink.fileno())
            temporary = Path(sink.name)
        os.chmod(temporary, 0o644)
        _validate_guards(guards or [])
        if original_body is None:
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise PublishError(
                    "baseline hash mismatch; refusing to overwrite concurrent update"
                ) from exc
            temporary.unlink()
            temporary = None
        else:
            _exchange_paths(temporary, target)
            displaced_body = temporary.read_bytes()
            if displaced_body != original_body:
                restored = _restore_exchanged_target(target, temporary, body)
                if not restored:
                    raise PublishError(
                        "baseline changed during publication; concurrent target was preserved"
                    )
                raise PublishError(
                    "baseline hash mismatch; refusing to overwrite concurrent update"
                )
        try:
            _validate_guards(guards or [])
        except PublishError as exc:
            if original_body is None:
                if target.read_bytes() == body:
                    target.unlink()
                else:
                    raise PublishError(
                        "guard changed during publication; concurrent target was preserved"
                    ) from exc
            else:
                try:
                    restored = _restore_exchanged_target(target, temporary, body)
                except OSError as rollback_exc:
                    raise PublishError(
                        "guard changed during publication and target rollback failed: "
                        f"{rollback_exc}"
                    ) from rollback_exc
                if not restored:
                    raise PublishError(
                        "guard changed during publication; concurrent target was preserved"
                    ) from exc
            raise PublishError("guard changed during publication; target was rolled back") from exc
        if target.read_bytes() != body:
            raise PublishError(
                "target changed immediately after publication; concurrent content was preserved"
            )
        return _sha256(body)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        os.close(lock_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish UTF-8 text only when the target baseline still matches."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument(
        "--guard",
        action="append",
        default=[],
        metavar="PATH:SHA256",
        help="Require another file to retain its expected SHA-256.",
    )
    args = parser.parse_args(argv)
    try:
        guards: list[tuple[Path, str]] = []
        for raw_guard in args.guard:
            try:
                raw_path, guard_sha256 = raw_guard.rsplit(":", 1)
            except ValueError as exc:
                raise PublishError("guard must use PATH:SHA256") from exc
            if (
                not raw_path
                or len(guard_sha256) != 64
                or any(character not in "0123456789abcdef" for character in guard_sha256)
            ):
                raise PublishError("guard must use PATH:SHA256")
            guards.append((Path(raw_path), guard_sha256))
        published_sha256 = publish_text(
            args.source,
            args.target,
            args.expected_sha256,
            guards,
        )
    except PublishError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(published_sha256)
    return 0


if __name__ == "__main__":
    sys.exit(main())
