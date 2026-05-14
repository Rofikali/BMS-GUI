# Native Core

The native core owns durability-sensitive infrastructure:

- file storage
- WAL
- checksums
- future recovery
- future indexing

Python and PySide6 must call this layer through stable APIs or bindings. They must not bypass it for critical persistence.

The core is pure C11:

- no C++
- no STL
- no exceptions
- no templates
- no C++ name mangling

Assembly is intentionally absent for now. It should be added only after profiling identifies a narrow hot path.
