from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a GitHub Release manifest for Slaoq Sniper V2.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--exe", default="dist/SlaoqSniper.exe")
    parser.add_argument("--output", default="manifest.json")
    parser.add_argument("--mandatory", action="store_true")
    parser.add_argument("--min-supported-version", default="1.0.0")
    parser.add_argument("--notes", default="Slaoq Sniper V2 release.")
    parser.add_argument("--notes-file", default="", help="Read multiline release notes from a UTF-8 text file.")
    args = parser.parse_args()

    exe = Path(args.exe)
    if not exe.exists():
        raise SystemExit(f"Executable not found: {exe}")

    notes = args.notes
    if args.notes_file:
        notes = Path(args.notes_file).read_text(encoding="utf-8").strip()

    manifest = {
        "version": args.version.lstrip("v"),
        "mandatory": bool(args.mandatory),
        "min_supported_version": args.min_supported_version.lstrip("v"),
        "asset_name": exe.name,
        "sha256": sha256_file(exe),
        "notes": notes,
    }
    Path(args.output).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(manifest["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
