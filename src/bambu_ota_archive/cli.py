from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .capture import Archiver
from .evidence import extract_log_file, resource_from_evidence
from .http import HttpClient
from .reconstruction import commit_reconstruction, import_git_reconstruction


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--user-agent", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    poll = subparsers.add_parser("poll", help="discover official families and poll the global API once")
    poll.add_argument("--commit", action="store_true", help="commit and tag every changed verified pack")
    poll.add_argument("--family", action="append", dest="families")
    poll.add_argument("--pause", type=float, default=0.2)

    extract = subparsers.add_parser("extract-log", help="extract only redacted OTA metadata from a Studio log")
    extract.add_argument("source", type=Path)
    extract.add_argument("destination", type=Path)
    extract.add_argument("--evidence-id", required=True)

    history = subparsers.add_parser("import-history", help="import reviewed historical evidence records")
    history.add_argument("manifest", type=Path)
    history.add_argument("--commit", action="store_true")

    reconstruct = subparsers.add_parser(
        "reconstruct-git", help="import a separate, explicitly unverified public-Git profile state"
    )
    reconstruct.add_argument("--source-repo", type=Path, required=True)
    reconstruct.add_argument("--revision", required=True)
    reconstruct.add_argument("--evidence", required=True)
    reconstruct.add_argument("--commit", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "extract-log":
        count = extract_log_file(args.source, args.destination, args.evidence_id)
        print(f"extracted {count} profile resource record(s)")
        return 0
    if args.command == "reconstruct-git":
        destination = import_git_reconstruction(args.root, args.source_repo, args.revision, args.evidence)
        if args.commit:
            commit_reconstruction(args.root, destination)
        print(destination)
        return 0
    client = HttpClient(**({"user_agent": args.user_agent} if args.user_agent else {}))
    if args.command == "poll":
        archiver = Archiver(args.root, client, commit=args.commit, pause=args.pause)
        results = archiver.poll(families=args.families)
        changed = [result for result in results if result.changed]
        print(json.dumps({"checked": len(results), "changed": len(changed), "tags": [r.tag for r in changed]}, indent=2))
        return 0
    if args.command == "import-history":
        archiver = Archiver(args.root, client, commit=args.commit)
        records = json.loads(args.manifest.read_text(encoding="utf-8"))
        for record in records:
            if record.get("metadata_only"):
                archiver.import_metadata_only(record)
                continue
            resource = resource_from_evidence(record)
            family = record.get("compatibility_family") or ".".join(resource.version.split(".")[:2])
            archiver.capture_resource(
                family,
                resource,
                provenance=record.get("provenance", "observed-log"),
                evidence=record["evidence"],
                observed_at=record["first_observed_at"],
                publication_time=record.get("publication_time"),
                uncertainty=record.get("uncertainty", []),
            )
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
