# Bambu Studio global OTA profile archive

This repository preserves evidence-backed profile packs returned by Bambu Lab's **global**
Bambu Studio resource API. It polls every officially published Studio 2.x-or-later minor
compatibility family and stores both the exact ZIP bytes and a safely expanded working tree.

This archive is intentionally **not described as historically complete**. The API returns only
the currently offered pack for a compatibility family. Varying the query patch version does not
enumerate older packs, and two upstream replacements within one hourly polling interval can make
the earlier pack permanently unobservable.

## Scope and invariants

- API: `https://api.bambulab.com/v1/iot-service/api/slicer/resource`
- Region: global only; no China endpoint or fallback exists in this project.
- Resource types: `slicer/settings/bbl` and, when actually returned, `slicer/printer/bbl`.
- Excluded: the API's `software` object, installers, plugins, firmware, authentication, hidden
  endpoints, directory listings, object-store APIs, guessed versions, and guessed CDN hashes.
- Family discovery: official `bambulab/BambuStudio` Git tags matching uppercase or lowercase
  `VMM.mm.pp.bb`, with major version 2 or later.
- Query: the family baseline `MM.mm.00.00`, every time, for every known family.
- Traffic: one combined resource request per family per run, with a transparent User-Agent and
  no aggressive retry loop.

## Repository layout

```text
families/02.00/settings/archive.zip
families/02.00/settings/contents/...
families/02.00/settings/metadata.json
catalog/observations.jsonl
catalog/current-inventory.json
reconstructions/git/<version>-<commit>/contents/...
reconstructions/git/<version>-<commit>/metadata.json
```

Each family/resource directory is a current tree. Ordinary Git history preserves prior trees and
same-version repacks. `catalog/observations.jsonl` is append-only and identifies observations by
family, type, version, URL, and archive SHA-256.

Verified archive tags use:

```text
ota/<family>/<settings-or-printer>/<pack-version>-<sha256-prefix>
```

They are annotated and unsigned. A URL or byte change with the same version produces a distinct
observation, commit, and tag marked `same_version_repack`.

## Run locally

Python 3.11 or later is sufficient; the archiver has no runtime dependencies.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m bambu_ota_archive.cli poll --commit
```

The committing mode requires a clean Git tree. It disables commit and tag signing explicitly.

To extract the minimum useful OTA metadata from a user-supplied Studio debug log without retaining
the log or unrelated personal data:

```bash
PYTHONPATH=src python -m bambu_ota_archive.cli extract-log \
  /path/to/debug.log evidence/reviewed-log.json \
  --evidence-id local-backup-2026-08-17
```

Review extracted metadata before using `import-history`. Never commit the source log.

## Archive validation

Downloads are never executed. Before expansion the archiver rejects absolute/traversing paths,
backslashes, NULs, links and other non-regular entries, duplicate and case-colliding paths,
excessive file counts or expanded size, suspicious compression ratios, CRC failures, truncated
ZIPs, and a missing/duplicate/mismatched `BBL.json`. Extraction copies original file bytes and
relative paths without reformatting JSON.

## Git reconstructions are not OTA packs

`reconstruct-git` may preserve a public BambuStudio profile tree in the separate
`reconstructions/git` namespace. It records the source commit and BBL subtree hash, creates no CDN
URL, receives no OTA tag, and is always classified `reconstructed-git`. Public Git state can help
explain profile evolution but is not evidence that a matching OTA was published or byte-identical.

## Automation and residual miss window

The workflow runs at minute 17 of every hour and supports manual dispatch. It tests first, uses
least-privilege `contents: write`, pins every action by full commit SHA, serializes runs without
cancelling an active capture, makes one commit per changed pack, creates annotated tags, and avoids
empty commits. GitHub schedules can be delayed; the effective miss window is the time between
successful runs, nominally one hour. Any pack replaced twice inside that window may be missed.

