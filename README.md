# Bambu Studio profile history

This repository is a file-level history of Bambu Lab's global Bambu Studio profile/settings
packs. Every known state is applied to the same `profiles/settings` path in chronological order,
so ordinary Git diffs show what Bambu added, removed, or changed between states.

The timeline combines two explicitly labeled evidence classes:

- `observed-api`: an exact ZIP returned by Bambu Lab's global OTA API, downloaded and validated.
- `reconstructed-git`: a profile tree reconstructed from an official public BambuStudio Git
  revision. It extends the useful timeline but is not evidence that the same bytes were released
  as an OTA pack.

Interleaving makes the files diffable; it does not erase or upgrade provenance. This archive is
also not historically complete: the API exposes only the pack currently offered to each
compatibility family, so older replacements may already be unavailable or may be missed between
polls.

## Browse and diff the profile history

The stable tree is:

```text
profiles/settings/BBL.json
profiles/settings/BBL/filament/...
profiles/settings/BBL/machine/...
profiles/settings/BBL/process/...
```

Useful commands:

```bash
# See every known profile state in order, with provenance tags.
git log --oneline --decorate -- profiles/settings

# Compare any two profile states.
git diff reconstructed-git/02.00.00.87-c9f4cbc94be3 \
  ota/02.00/settings/02.00.00.91-852e4790a1fa -- profiles/settings

# Follow one profile through renames and edits.
git log --follow -p -- \
  'profiles/settings/BBL/filament/Bambu PLA Basic @base.json'
```

`timeline/settings.json` describes the state checked out at a timeline commit and points to its
immutable source record. The complete initial ordering and identifiers are in `REPORT.md`.

## Repository layout

```text
profiles/settings/...                                      current diffable tree
timeline/settings.json                                     current state's provenance
sources/ota/<family>/settings/<version>-<sha>/archive.zip  exact verified OTA bytes
sources/ota/<family>/settings/<version>-<sha>/metadata.json
sources/git/<version>-<commit>/metadata.json               Git reconstruction evidence
catalog/observations.jsonl                                 append-only OTA observations
catalog/current-inventory.json                             latest global API response
```

Source records accumulate and are never substituted for one another. The extracted profile tree
is intentionally singular: each history commit replaces that path with the next known state.

Verified OTA tags use:

```text
ota/<family>/<settings-or-printer>/<pack-version>-<sha256-prefix>
```

Git-derived states use:

```text
reconstructed-git/<pack-version>-<source-commit-prefix>
```

Both are annotated and unsigned. A URL or byte change with the same OTA version produces a new
observation, commit, and OTA tag marked `same_version_repack`.

## Scope and invariants

- API: `https://api.bambulab.com/v1/iot-service/api/slicer/resource`
- Region: global only; there is no China endpoint or fallback in this project.
- Resource types: `slicer/settings/bbl` and, if returned, `slicer/printer/bbl`.
- Excluded: software objects, installers, plugins, firmware, authentication, hidden endpoints,
  directory listings, object-store APIs, guessed versions, and guessed CDN hashes.
- Download allowlist: exact HTTPS `.../upgrade/studio/{settings|printer}/BBL/.../<version>.zip`
  paths on `public-cdn.bblmw.com`; query strings, cross-host redirects, and type/version path
  mismatches are rejected.
- Family discovery: official `bambulab/BambuStudio` tags matching uppercase or lowercase
  `VMM.mm.pp.bb`, with major version 2 or later.
- Query: every known family's `MM.mm.00.00` baseline on every run.
- Traffic: one combined request per family per run, a transparent User-Agent, and low retry volume.
- Published history is append-only. An unexpectedly late state is recorded with its true
  provenance and observation time; published commits are never reordered.

## Run locally

Python 3.11 or later is sufficient; the archiver has no runtime dependencies.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m bambu_ota_archive.cli audit
PYTHONPATH=src python -m bambu_ota_archive.cli poll --commit
```

Committing mode requires a clean Git tree and explicitly disables commit and tag signing.

To extract the minimum useful OTA metadata from a user-supplied Studio debug log without retaining
the log or unrelated personal data:

```bash
PYTHONPATH=src python -m bambu_ota_archive.cli extract-log \
  /path/to/debug.log evidence/reviewed-log.json \
  --evidence-id local-backup-2026-08-17
```

Review extracted metadata before using `import-history`. Never commit the source log.

## Archive validation

Downloads are never executed. Before expansion the archiver rejects absolute or traversing paths,
backslashes, NULs, links and other non-regular entries, duplicate and case-colliding paths,
excessive file counts or expanded size, suspicious compression ratios, CRC failures, truncated
ZIPs, and a missing, duplicate, or mismatched `BBL.json`. Extraction preserves original file bytes
and relative paths without reformatting JSON.

## Automation and residual miss window

The workflow runs at minute 17 of every hour and supports manual dispatch. It tests and audits
first, uses least-privilege `contents: write`, pins actions by full commit SHA, serializes captures,
makes one timeline commit per changed pack, creates annotated tags, and avoids empty commits.

GitHub schedules can be delayed. The effective miss window is the time between successful runs,
nominally one hour. A pack replaced twice inside that window can disappear without being observed.
