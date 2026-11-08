"""Validate the runtime against the committed target-specific artifact lock."""
import hashlib
import importlib.metadata
import platform
import re
from pathlib import Path


def text_digest(path):
    return hashlib.sha256(Path(path).read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest()


def verify_environment(root):
    root = Path(root)
    expected_python = (root / ".python-version").read_text().strip()
    if (platform.python_version() != expected_python or platform.system() != "Windows"
            or platform.machine().lower() != "amd64" or platform.python_implementation() != "CPython"):
        raise ValueError(f"Use CPython {expected_python} on Windows AMD64 for this lock")
    lines = (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
    expected = {}
    for line in lines:
        match = re.fullmatch(r"([a-z0-9-]+)==([^ ]+) --hash=sha256:([0-9a-f]{64})", line)
        if match:
            expected[match[1]] = match[2]
        elif line.strip() and not line.startswith(("#", "--only-binary=")):
            raise ValueError("Unexpected lock entry")
    if not expected:
        raise ValueError("Empty dependency lock")
    if not any(line == f"# requirements.in sha256: {text_digest(root / 'requirements.in')}" for line in lines):
        raise ValueError("requirements.in changed; regenerate the lock")
    mismatches = []
    actual = {}
    for name, version in expected.items():
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = "missing"
        actual[name] = installed
        if installed != version:
            mismatches.append(f"{name}: expected {version}, found {installed}")
    if mismatches:
        raise ValueError("Environment does not match lock: " + "; ".join(mismatches))
    return dict(python=platform.python_version(), implementation=platform.python_implementation(),
                system=platform.system(), machine=platform.machine(), packages=actual,
                requirements_sha256=text_digest(root / "requirements.txt"))


if __name__ == "__main__":
    identity = verify_environment(Path(__file__).resolve().parents[1])
    print(f"Environment matches lock: {len(identity['packages'])} packages; CPython {identity['python']}, Windows AMD64")
