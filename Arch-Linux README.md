# BMS-GUI

BMS-GUI is an offline-first desktop business management system for retail and inventory-heavy businesses. The goal is not a simple billing app; it is an accounting-correct operating platform that can grow into a durable business, inventory, audit, and reporting system.

The product is designed from three perspectives:

- CA: accounting correctness, auditability, reconciliation, tax readiness, and ledger integrity.
- MBA: operational intelligence, profitability, inventory visibility, and business decision support.
- Engineer: native durability, clear module boundaries, testable contracts, and long-term maintainability.

## Architecture

The platform starts as a modular monolith:

```text
PySide6 UI -> Python services -> C API -> native C11 core -> file-based durable storage
```

Core storage and durability code lives in `core/` and is implemented in pure C11. Assembly is allowed only for narrow hot paths after profiling proves it is needed. Python and PySide6 sit above the native boundary and must not bypass the C durability path.

MVP storage is file-based first, using append-only records, checksums, WAL support, and rebuildable read models. The decision is documented in [docs/ADR/0002-file-based-storage-for-mvp.md](docs/ADR/0002-file-based-storage-for-mvp.md) and [docs/FILE_STORAGE_SPEC.md](docs/FILE_STORAGE_SPEC.md).

## Documentation

Start at [docs/README.md](docs/README.md).

The canonical product and engineering source of truth is [docs/PLATFORM_SPEC.md](docs/PLATFORM_SPEC.md). If other documents conflict with it, the platform spec wins until an ADR changes the decision.

Useful entry points:

- [docs/VISION.md](docs/VISION.md) - long-term mission and product ambition
- [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md) - first production-grade release boundary
- [docs/IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) - first build order
- [docs/FIRST_TEST_PLAN.md](docs/FIRST_TEST_PLAN.md) - first verification plan
- [docs/BUSINESS_STRATEGY.md](docs/BUSINESS_STRATEGY.md) - target customer and business model

## Build And Test

Build the native core:

```bash
cmake -S . -B build -G Ninja
cmake --build build
```

Run core tests:

```bash
ctest --test-dir build --output-on-failure
```

Run checksum-focused tests:

```bash
ctest --test-dir build -R checksum --output-on-failure
```

```all passed what should be next steps as a principle/stuff enginner
Use pydantic if better as a stuff/principle enginner here
cmake -S . -B build -G Ninja
cmake --build build
ctest --test-dir build --output-on-failure
PYTHONPATH=src python3 -m unittest discover tests/unit
```
# 🧠 CODESPACES ARCH LINUX ENV

### Automated Containerized Development Environment Setup

![Environment](https://shields.io)
![Platform](https://shields.io)
![Status](https://shields.io)

`codespaces-arch` is a comprehensive engineering guide and workflow blueprint for initializing, troubleshooting, and running a micro-minimal Arch Linux development environment directly inside GitHub Codespaces.

Designed for **systems engineers and kernel developers**, it handles containerized package bootstrapping, filesystem security boundaries, and multi-user Git identity hooks.

---

## 🔷 Overview

This environment workflow runs a **lightweight Arch userspace container**, optimized for:

- ⚡ Rapid package deployment (`pacman`)
- 🛠️ Native host compilation (`base-devel`, `cmake`)
- 🔐 Secure repository access (UID mapping control)
- 🖨️ Clean text pipelines (`less` pager alignment)

---

## ⚡ Features

- ✅ Unified system dependency bootstrapping
- ✅ Git Large File Storage (LFS) pre-push pipeline setup
- ✅ Cross-UID container security mapping (Dubious Ownership fixes)
- ✅ Automated environment identity binding
- ✅ Native terminal paging correction
- ✅ Matrix comparison for Debian-to-Arch adaptation

---

## 📦 Installation

### Requirements

- GitHub Codespaces instance
- Base image with root/sudo capabilities

---

### Build & Initialize Environment

    --- bash ---
    # Step 1: Force system synchronization and full upgrade
    sudo pacman -Syu

    # Step 2: Provision toolchains and core utilities
    sudo pacman -S base-devel git neovim less git-lfs cmake ninja perf

    # Step 3: Global initialization of Git LFS hooks
    git lfs install

---

## 🧑‍💻 Configuration

    Basic Syntax
    git config --global [OPTION] [VALUE]

## 📥 Environment Diagnostics

    Error Pattern Root Cause Target Resolution
    fatal: detected dubious ownership Host UID (1000) vs Container Root Register safe directory configuration
    fatal: author identity unknown Missing local profile hooks Inject global user name and email
    cannot run less: No such file Native package absence Provision less utility via pacman

## ⚙️ Configuration Flags

    🔹 Git Identity Tuning
    Option Description Target Value
    user.name Developer name Rofik
    user.email Primary notification email alirofikr@gmail.com

## Security Boundaries

    Option Description Target Value
    safe.directory Whitelists shared workspace root /workspaces/SecureCleaner-Kernel

---

## 🧠 Processing Pipeline

    Host Workspace File Injection (UID 1000)
       ↓
    Container Access Attempt (Root Context)
       ↓
    Git Security Intercept (Dubious Ownership Block)
       ↓
    Safe Directory Override (Whitelisting)
       ↓
    Identity Alignment (Name + Email Injection)
       ↓
    LFS Hook Registration (Pre-Push Asset Binding)
       ↓
    Secure Remote Sync (GitHub Personal Access Token)

---

## 🧪 Deployment Workflows

    1. Environment Onboarding
    sudo pacman -Syu && sudo pacman -S base-devel git neovim less git-lfs cmake ninja perf && git lfs install

    2. Bypass Filesystem Ownership Security Block
    git config --global --add safe.directory /workspaces/SecureCleaner-Kernel

    3. Local User Registration
    git config --global user.name "Rofik"
    git config --global user.email "alirofikr@gmail.com"

    4. Asset Upload Sequence
    git add .
    git commit -m "chore: migrate runtime environment to arch linux userspace"
    git push

---

## 🚀 Architecture

    Core Components
    Containerized Userspace
    Runs Arch components inside Docker
    Shares underlying host system kernel
    Bypasses native systemd service layers
    Git Security Model
    Strict boundary policy checks on UIDs
    Prevents unauthorized context execution
    Dependency Chain
    Decoupled toolchains (cmake/ninja)
    Unified via Arch package databases

---

## ⚡ Command Mapping

    Action Debian/Ubuntu Command Arch Linux Command
    Sync Repositories apt update ❌ (Do not use partial syncs)
    Upgrade System apt upgrade pacman -Syu
    Install Utilities apt install [pkg] pacman -S [pkg]

---

## 📝 Best Practices

    Always run 'pacman -Syu' instead of partial syncs ('-Sy')
    Use a Personal Access Token (PAT) for remote auth (not password)
    Bind global configs specifically inside the root user scope

---

## 🔮 Roadmap

     Automate pipeline via .devcontainer.json
     Abstract root access to custom non-root accounts
     Build a custom Pacman local mirror cache

---

## 🤝 Contributing

    Issues and optimization PRs are welcome.

---

## 📄 License

    MIT License
