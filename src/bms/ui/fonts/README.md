Bundled font directory for Qt deployments.

Qt checks `QT_QPA_FONTDIR` during startup on some platforms. Keeping this
application-owned directory in the package avoids depending on a PySide
installation-specific `lib/fonts` path.
