# BMS-GUI

Documentation starts at [docs/README.md](docs/README.md).

The canonical product and engineering source of truth is [docs/PLATFORM_SPEC.md](docs/PLATFORM_SPEC.md).

The MVP storage decision is file-based first, documented in [docs/ADR/0002-file-based-storage-for-mvp.md](docs/ADR/0002-file-based-storage-for-mvp.md) and [docs/FILE_STORAGE_SPEC.md](docs/FILE_STORAGE_SPEC.md).

Native core work starts in `core/`; Python and PySide6 are integration layers above the C API.


cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure

