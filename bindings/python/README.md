# Python Bindings

Python bindings will be added after the C storage/WAL API stabilizes.

The intended boundary is:

```text
PySide6 UI
-> Python application services
-> Python bindings
-> C core
```

No critical storage logic belongs in Python.
