# Initial archive report

Live capture: **2026-08-17T20:51:23Z**  
Endpoint: global Bambu service only  
Official families discovered: **02.00 through 02.08**

## Linear profile timeline

The initial history applies all 16 available states to one stable `profiles/settings` tree. The
order below is strictly increasing by the best available source time and also by pack version.
`reconstructed-git` rows extend the diffable record but remain explicitly unverified as OTA.

| Source time | Pack | Provenance | Tag |
|---|---|---|---|
| 2025-04-24 11:19:29 UTC | 02.00.00.87 | reconstructed-git | `reconstructed-git/02.00.00.87-c9f4cbc94be3` |
| 2025-05-22 04:16:59 UTC | 02.00.00.91 | observed-api | `ota/02.00/settings/02.00.00.91-852e4790a1fa` |
| 2025-06-16 11:43:27 UTC | 02.01.00.18 | reconstructed-git | `reconstructed-git/02.01.00.18-456a87de5ee4` |
| 2025-07-29 11:46:38 UTC | 02.01.00.19 | observed-api | `ota/02.01/settings/02.01.00.19-3c58b1aceba7` |
| 2025-08-15 09:54:12 UTC | 02.02.00.02 | observed-api | `ota/02.02/settings/02.02.00.02-d13fbfb7aabb` |
| 2025-09-15 09:13:09 UTC | 02.02.00.04 | reconstructed-git | `reconstructed-git/02.02.00.04-4f0f0f3e9740` |
| 2025-10-30 04:28:20 UTC | 02.03.00.04 | reconstructed-git | `reconstructed-git/02.03.00.04-1241f815dc78` |
| 2025-11-05 11:55:52 UTC | 02.03.00.05 | observed-api | `ota/02.03/settings/02.03.00.05-bd34995524d7` |
| 2025-11-18 12:51:31 UTC | 02.04.00.01 | reconstructed-git | `reconstructed-git/02.04.00.01-b6bafe4eadf7` |
| 2025-12-29 08:53:52 UTC | 02.04.00.10 | observed-api | `ota/02.04/settings/02.04.00.10-b753a638d8d1` |
| 2026-03-18 12:11:17 UTC | 02.05.00.14 | observed-api | `ota/02.05/settings/02.05.00.14-0d97aa41d26a` |
| 2026-04-15 07:29:38 UTC | 02.05.00.18 | reconstructed-git | `reconstructed-git/02.05.00.18-0829bc5f18bd` |
| 2026-04-28 13:58:43 UTC | 02.06.00.03 | reconstructed-git | `reconstructed-git/02.06.00.03-6eb52d6ac75e` |
| 2026-05-19 06:12:10 UTC | 02.06.00.05 | observed-api | `ota/02.06/settings/02.06.00.05-774ee3474b28` |
| 2026-06-16 13:24:01 UTC | 02.07.00.08 | reconstructed-git | `reconstructed-git/02.07.00.08-42d319c6692f` |
| 2026-08-14 11:47:48 UTC | 02.08.00.04 | reconstructed-git | `reconstructed-git/02.08.00.04-9a530f77c23d` |

## Current global inventory

| Family | Resource | Pack | SHA-256 | CDN Last-Modified |
|---|---|---|---|---|
| 02.00 | settings | 02.00.00.91 | `852e4790a1faa61905df1cdf82782e98ed00ef1255a7b1889d7fe7e46a912b63` | 2025-05-22 04:16:59 UTC |
| 02.01 | settings | 02.01.00.19 | `3c58b1aceba705b33f0fed033e998e3c3f6397a2c8dccc27dff41e49a2ce579f` | 2025-07-29 11:46:38 UTC |
| 02.02 | settings | 02.02.00.02 | `d13fbfb7aabb9aee567d836cf6ef4ac2f5dffaa255cda94be0c2223d4d827aa6` | 2025-08-15 09:54:12 UTC |
| 02.03 | settings | 02.03.00.05 | `bd34995524d71cb616df2aabc5614cdc568e5d173b6245468a9b49f22b253678` | 2025-11-05 11:55:52 UTC |
| 02.04 | settings | 02.04.00.10 | `b753a638d8d1685ced5c67985fe4d915fc0ebfcaf201372f5079d0688c9c17eb` | 2025-12-29 08:53:52 UTC |
| 02.05 | settings | 02.05.00.14 | `0d97aa41d26aea868c3129fff44a0710b53a8a3428629973d7bb13191e9d0326` | 2026-03-18 12:11:17 UTC |
| 02.06 | settings | 02.06.00.05 | `774ee3474b28315a2dfe5fe276fa3f035ed6dcdde77a70f30ca848be0fda4c70` | 2026-05-19 06:12:10 UTC |
| 02.07 | none returned | — | — | — |
| 02.08 | none returned | — | — | — |

The global API returned no `slicer/printer/bbl` package for any family. Every family was still
queried for it in the same single request as settings. The first-run catalog matched the supplied
seed for all nine families.

## Exact verified URLs

All seven were directly observed in the global API, downloaded successfully, hashed, safely
expanded, and validated against their internal `BBL.json` version:

1. `https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.00.00.91/22021b5541/02.00.00.91.zip`
2. `https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.01.00.19/fb728ec9c9/02.01.00.19.zip`
3. `https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.02.00.02/7d8cdaa553/02.02.00.02.zip`
4. `https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.03.00.05/8a4f7ed7b3/02.03.00.05.zip`
5. `https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.04.00.10/ebf18539c1/02.04.00.10.zip`
6. `https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.05.00.14/94e1473172/02.05.00.14.zip`
7. `https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.06.00.05/ebc7c9ad1d/02.06.00.05.zip`

These are current packs, not recovered superseded packs. The public historical evidence pass found
no exact superseded global Studio 2.x URL. Consequently there are no metadata-only records and no
superseded historical archive whose continued download availability can be reported. See
`evidence/research-notes.md` for the bounded search record.

## Git reconstructions

Nine representative states—the latest official release tag in each 2.0–2.8 family at capture
time—have source records under `sources/git` and profile trees in their tagged timeline commits.
Each records its exact source commit, BBL subtree, and `BBL.json` blob. None has a CDN URL or OTA
tag, and none is treated as published OTA proof.

The initial reconstruction intentionally remains bounded to those nine representative states.
`state/studio-releases.json` records all 33 official Studio 2.x tags that existed when continuous
automation began, distinguishing the nine captured snapshots from older baseline-only tags. Every
official Studio 2.x tag first observed after that baseline is now captured automatically and
interleaved with OTA states; published history is not rewritten to backfill the other old tags.

| Studio tag | BBL.json version | Source commit |
|---|---|---|
| V02.00.03.54 | 02.00.00.87 | `c9f4cbc94be325dfda6ab694ddec2cfffe482284` |
| v02.01.01.52 | 02.01.00.18 | `456a87de5ee44ce67fbcda3f83dd1c31d199319c` |
| v02.02.02.56 | 02.02.00.04 | `4f0f0f3e97400629205048995c77b5eedd2768e5` |
| v02.03.01.51 | 02.03.00.04 | `1241f815dc784c748d75532c9fd722241d253fd2` |
| v02.04.00.70 | 02.04.00.01 | `b6bafe4eadf75c177a53837ba9bd10eb5be9d84f` |
| v02.05.03.62 | 02.05.00.18 | `0829bc5f18bddc372db815f706384e7c4284bcb5` |
| v02.06.01.55 | 02.06.00.03 | `6eb52d6ac75e32ba2116239c1d756d913053f364` |
| v02.07.01.62 | 02.07.00.08 | `42d319c6692fa8e64790fddf0cdaafd2a4254bcc` |
| v02.08.02.60 | 02.08.00.04 | `9a530f77c23d8c3430d1dbef02e103cd8bd6480e` |

The differing live OTA and Git versions demonstrate why Git content cannot substitute for OTA
evidence.

## Automation, verification, and residual risk

The pinned-SHA GitHub Actions workflow runs hourly at minute 17 and on manual dispatch. It has
`contents: write` only, concurrency serialization, tests before capture, no empty commits, one
commit per changed OTA pack or new Studio release snapshot, and an annotated provenance tag per
timeline state. It maintains a small cached blob-filtered mirror of official BambuStudio tag
metadata, fetches profile blobs only for unseen releases, and keeps those large blobs out of the
recurring cache. The checkout and cache action SHAs were verified against
their official tags on 2026-08-17.

The local suite contains **41 tests** covering the stable diffable tree, latest-only behavior, empty
responses, versions and repacks, new/old families, history imports, metadata-only records, Git
separation, release/OTA ordering in both directions, combined-sync idempotence, log redaction, and
every enumerated unsafe ZIP case. The live run validated 7 archives containing
11,070 ZIP entries in total. The repository audit independently rehashed and revalidated all 7
stored archives, confirmed 7 unique catalog observations, checked all 9 reconstruction
classifications, validated the 33-tag Studio release ledger, and checked the checked-out
timeline/source linkage.

The nominal polling interval leaves a one-hour miss window; GitHub schedule delays or failed runs
make the effective window longer. Since the API exposes only the pack currently offered to each
family, any pack replaced twice between successful runs can disappear without ever being observed.
Changing the query version cannot enumerate it. Historical completeness therefore cannot be
guaranteed now or later.
