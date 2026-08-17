# Historical evidence search notes

Search performed 2026-08-17. These notes record the bounded public search and its negative result;
they do not claim that every possible private backup, cache, or unindexed page was searched.

## Exact superseded global Studio 2.x OTA URLs recovered

None.

The seven URLs in `catalog/current-inventory.json` were observed directly in the live global API
and were still the currently offered packs. They are not presented as superseded historical finds.

## Sources checked

- Official `bambulab/BambuStudio` releases and tags, including both `v` and `V` prefixes. These
  established published compatibility families 2.0 through 2.8 and supplied the separate Git
  reconstruction inputs.
- Public BambuStudio GitHub issues and comments searched for `slicer/settings/bbl`,
  `request_resources`, `BBL Updater`, `public-cdn.bblmw.com`, and 2.x version fragments. No exact
  superseded 2.x settings URL was returned. Issue
  [#5266](https://github.com/bambulab/BambuStudio/issues/5266) contains a useful exact updater
  response for Studio 1.10, but it was excluded by the Studio-2+ scope.
- GitHub public code search for the full CDN path, the resource type, and known 2.x filenames. No
  additional indexed source was returned.
- General web search for each 2.0 through 2.6 CDN version prefix, excluding the known live hash.
  No additional exact URL was returned.
- Internet Archive CDX queries for the global API path and the 2.x settings-CDN prefix. Both
  returned an empty capture list.
- Common Crawl indexes `CC-MAIN-2025-13` through `CC-MAIN-2026-30`, queried at low rate for the
  2.x settings-CDN prefix. Every index returned no capture; the one initial timeout was retried
  successfully.

No raw public debug log was retained. No Chinese endpoint, guessed URL, guessed version, CDN hash
brute force, object-store API, directory listing, authentication, installer, plugin, firmware, or
API `software` URL was queried or downloaded.

## Evidence still worth seeking

The highest-value missing sources are user-supplied Bambu Studio data-directory backups,
`ota/presets` caches, and debug logs from 2025–2026. The `extract-log` command emits only approved
resource metadata and discards unrelated log text and sensitive fields. Any extracted URL still
requires a CDN retrieval attempt and internal `BBL.json` validation before it can become
`retrieved-cdn`; unavailable URLs remain `metadata-only`.

