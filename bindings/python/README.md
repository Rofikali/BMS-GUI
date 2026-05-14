# Python Binding Boundary

The Python layer loads the native C11 durability core through `ctypes`.

Build the shared library first:

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

Then run Python tooling with uv:

```sh
uv sync
uv run bms-core-smoke
uv run bms-gui


python3 -m uv run bms-core-smoke
python3 -m uv run python -m unittest tests.unit.test_core_file_store tests.unit.test_accounting_service

```

The UI and Python services must call application services and this binding layer.
They must not open critical storage files directly.
