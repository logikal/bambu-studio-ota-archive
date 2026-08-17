from __future__ import annotations

API_ENDPOINT = "https://api.bambulab.com/v1/iot-service/api/slicer/resource"
GITHUB_TAGS_ENDPOINT = "https://api.github.com/repos/bambulab/BambuStudio/tags"
ALLOWED_RESOURCE_TYPES = frozenset({"slicer/settings/bbl", "slicer/printer/bbl"})
MAIN_RESOURCE_TYPE = "slicer/settings/bbl"
PRINTER_RESOURCE_TYPE = "slicer/printer/bbl"
DEFAULT_USER_AGENT = (
    "bambu-studio-ota-archive/0.1 "
    "(global OTA profile preservation; contact: https://github.com/logikal)"
)

# Conservative safety limits. They are intentionally configurable by callers in tests.
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_FILES = 100_000
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000.0
