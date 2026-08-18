# Bambu Studio profile history

## What

This repository keeps a chronological history of Bambu Studio's built-in printer, filament, and
process profiles. Every captured version is stored at the same `profiles/settings` path, so a
normal Git diff shows exactly what Bambu added, removed, or changed.

## Why

Bambu changes profiles in two ways:

1. A new Bambu Studio release includes a set of profiles.
2. Bambu can update those profiles over the air without releasing a new version of Studio.

The next Studio release usually includes the OTA fixes plus additional changes. To show the real
sequence, this repository interleaves both sources in one timeline:

```text
Studio release → OTA update → OTA update → Studio release → OTA update
```

## How

An hourly GitHub Actions job checks both the official BambuStudio release tags and Bambu's global
profile-update API. When it finds a new state, it validates the files and appends one commit to the
timeline. If nothing changed, it creates no commit.

Each commit clearly identifies its source:

- `observed-api` means the exact OTA ZIP was downloaded from Bambu and validated.
- `reconstructed-git` means the profiles came from an official BambuStudio release tag. This is
  useful release evidence, but it does not claim those exact bytes were also distributed by OTA.

The archive cannot guarantee a complete history from before monitoring began. It can also miss an
OTA pack if Bambu replaces it twice between successful hourly checks. Studio release tags do not
normally have that one-hour miss window because they can be captured on a later run.

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
state/studio-releases.json                                 official Studio tags already handled
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
- Studio releases: every newly observed official `bambulab/BambuStudio` tag matching uppercase or
  lowercase `VMM.mm.pp.bb`, with major version 2 or later, contributes its bundled
  `resources/profiles/BBL` snapshot.
- OTA discovery: every known Studio major/minor line is queried at its `MM.mm.00.00` baseline on
  every run, including old lines, so profile-only fixes do not depend on a new Studio release.
- Traffic: one combined request per family per run, a transparent User-Agent, and low retry volume.
- Published history is append-only. An unexpectedly late state is recorded with its true
  provenance and observation time; published commits are never reordered.

## Run locally

Python 3.11 or later is sufficient; the archiver has no runtime dependencies.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m bambu_ota_archive.cli audit
PYTHONPATH=src python -m bambu_ota_archive.cli poll --commit
PYTHONPATH=src python -m bambu_ota_archive.cli sync \
  --source-repo /path/to/BambuStudio.git --commit
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
makes one timeline commit per new Studio snapshot or changed OTA pack, creates annotated tags, and
avoids empty commits.

Each run refreshes a small cached, blob-filtered Git mirror containing the official BambuStudio
tag metadata. Profile blobs are downloaded only for unseen release tags and are deliberately not
added to the recurring cache. New Studio snapshots and OTA packs first seen in the same run are
sorted by the Studio tag's release time and the CDN `Last-Modified` time before they are committed.
Their metadata also records when this archive first observed them.

GitHub schedules can be delayed. The effective miss window is the time between successful runs,
nominally one hour. A pack replaced twice inside that window can disappear without being observed.
Official Git tags remain discoverable on later runs, so this miss window applies to replaceable OTA
offers, not ordinarily to Studio release snapshots.
