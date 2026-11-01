#!/usr/bin/env python3
"""Keep manifest.json and const.py versions aligned.

Usage:
    python scripts/bump_versions.py --check
    python scripts/bump_versions.py --part patch|minor|major
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "custom_components" / "lightcompanion"
MANIFEST_PATH = PKG / "manifest.json"
CONST_PATH = PKG / "const.py"


def get_manifest_version() -> str:
    return str(json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["version"])


def get_const_version() -> str:
    text = CONST_PATH.read_text(encoding="utf-8")
    match = re.search(r'^VERSION\s*=\s*"(\d+\.\d+\.\d+)"', text, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


def check_versions() -> bool:
    manifest, const = get_manifest_version(), get_const_version()
    print(f"manifest.json:  {manifest}")
    print(f"const.py:       {const}")
    if manifest == const:
        print("\nAll versions aligned.")
        return True
    print("\nERROR: Version mismatch detected!")
    return False


def bump_version(current: str, part: str) -> str:
    major, minor, patch = map(int, current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def set_version(new_version: str) -> None:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    data["version"] = new_version
    MANIFEST_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    text = CONST_PATH.read_text(encoding="utf-8")
    text = re.sub(r'^(VERSION\s*=\s*)"[^"]*"', f'\\1"{new_version}"', text, flags=re.MULTILINE)
    CONST_PATH.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Version management")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--part", choices=["patch", "minor", "major"])
    args = parser.parse_args()
    if args.check:
        sys.exit(0 if check_versions() else 1)
    if args.part:
        new = bump_version(get_manifest_version(), args.part)
        set_version(new)
        print(f"Version bumped to {new}")
        check_versions()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
