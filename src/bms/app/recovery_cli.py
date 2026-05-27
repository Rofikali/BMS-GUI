from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence, TextIO

from bms.app.recovery import (
    ApplicationRecoveryError,
    export_application_recovery_diagnostics,
    export_application_recovery_report,
    reconcile_recovery_transaction,
    recover_application_storage,
    resolve_recovery_accounting_adjustment,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "inspect":
        return _inspect(args.data_root, sys.stdout, sys.stderr)
    if args.command == "recover":
        return _recover(args.data_root, sys.stdout, sys.stderr)
    if args.command == "report":
        return _report(args.data_root, sys.stdout, sys.stderr)
    if args.command == "reconcile":
        return _reconcile(
            args.data_root,
            args.transaction_id,
            args.decision,
            args.actor_id,
            args.reason,
            sys.stdout,
            sys.stderr,
        )
    if args.command == "resolve-accounting-adjustment":
        return _resolve_accounting_adjustment(
            args.data_root,
            args.transaction_id,
            args.actor_id,
            args.reason,
            args.journal_json,
            sys.stdout,
            sys.stderr,
        )
    parser.error("unknown command")
    return 2


def _inspect(data_root: Path, stdout: TextIO, stderr: TextIO) -> int:
    try:
        diagnostics = export_application_recovery_diagnostics(data_root)
    except Exception as exc:
        _write_json(stderr, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 2

    _write_json(stdout, {"ok": True, **diagnostics})
    if diagnostics["startup_health"]["state"] == "protected_mode":
        return 3
    if diagnostics["automatic_recovery_safe"]:
        return 0
    return 4


def _recover(data_root: Path, stdout: TextIO, stderr: TextIO) -> int:
    try:
        diagnostics = export_application_recovery_diagnostics(data_root)
    except Exception as exc:
        _write_json(stderr, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 2
    if diagnostics["startup_health"]["state"] == "protected_mode":
        _write_json(
            stderr,
            {
                "ok": False,
                "error": diagnostics["startup_health"]["message"],
                "diagnostics": diagnostics,
            },
        )
        return 3
    if not diagnostics["automatic_recovery_safe"]:
        _write_json(
            stderr,
            {
                "ok": False,
                "error": "manual reconciliation required before automatic recovery",
                "diagnostics": diagnostics,
            },
        )
        return 4

    try:
        result = recover_application_storage(data_root)
    except ApplicationRecoveryError as exc:
        _write_json(stderr, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 4
    except Exception as exc:
        _write_json(stderr, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 2

    _write_json(
        stdout,
        {
            "ok": True,
            "before": {
                "state": result.before.state.value,
                "message": result.before.message,
                "wal_status": result.before.wal_status,
                "wal_decision": result.before.wal_decision,
            },
            "recovery": {
                "status": result.recovery.status,
                "decision": result.recovery.decision,
            },
            "after": {
                "state": result.after.state.value,
                "message": result.after.message,
                "wal_status": result.after.wal_status,
                "wal_decision": result.after.wal_decision,
            },
        },
    )
    return 0


def _report(data_root: Path, stdout: TextIO, stderr: TextIO) -> int:
    try:
        report = export_application_recovery_report(data_root)
    except Exception as exc:
        _write_json(stderr, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 2

    _write_json(stdout, {"ok": True, **report})
    if report["startup_health"]["state"] == "protected_mode":
        return 3
    if report["normal_startup_allowed"]:
        return 0
    if report["recommended_next_action"] == "run_bms_recovery_recover":
        return 0
    return 4


def _reconcile(
    data_root: Path,
    transaction_id: str,
    decision: str,
    actor_id: str,
    reason: str,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        result = reconcile_recovery_transaction(
            data_root,
            transaction_id=transaction_id,
            decision=decision,
            actor_id=actor_id,
            reason=reason,
        )
    except ApplicationRecoveryError as exc:
        _write_json(stderr, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 4
    except Exception as exc:
        _write_json(stderr, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 2

    _write_json(
        stdout,
        {
            "ok": True,
            "reconciliation_id": result.reconciliation_id,
            "transaction_id": result.transaction_id,
            "decision": result.decision.value,
            "resolved": result.resolved,
        },
    )
    return 0


def _resolve_accounting_adjustment(
    data_root: Path,
    transaction_id: str,
    actor_id: str,
    reason: str,
    journal_json: str,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        journal_payload = json.loads(journal_json)
        if not isinstance(journal_payload, dict):
            raise ApplicationRecoveryError("journal-json must decode to an object")
        result = resolve_recovery_accounting_adjustment(
            data_root,
            transaction_id=transaction_id,
            actor_id=actor_id,
            reason=reason,
            journal_payload=journal_payload,
        )
    except ApplicationRecoveryError as exc:
        _write_json(stderr, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 4
    except Exception as exc:
        _write_json(stderr, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        return 2

    _write_json(
        stdout,
        {
            "ok": True,
            "reconciliation_id": result.reconciliation_id,
            "transaction_id": result.transaction_id,
            "correction_journal_id": result.correction_journal_id,
            "resolved": result.resolved,
        },
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bms-recovery")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="inspect recovery state without mutating storage")
    inspect_parser.add_argument("--data-root", type=Path, required=True)

    recover_parser = subparsers.add_parser("recover", help="run automatic recovery when diagnostics say it is safe")
    recover_parser.add_argument("--data-root", type=Path, required=True)

    report_parser = subparsers.add_parser("report", help="export a support-friendly recovery report")
    report_parser.add_argument("--data-root", type=Path, required=True)

    reconcile_parser = subparsers.add_parser("reconcile", help="record a manual recovery reconciliation decision")
    reconcile_parser.add_argument("--data-root", type=Path, required=True)
    reconcile_parser.add_argument("--transaction-id", required=True)
    reconcile_parser.add_argument("--decision", required=True)
    reconcile_parser.add_argument("--actor-id", required=True)
    reconcile_parser.add_argument("--reason", required=True)

    adjustment_parser = subparsers.add_parser(
        "resolve-accounting-adjustment",
        help="post a correction journal and resolve a transaction reconciled as requiring accounting adjustment",
    )
    adjustment_parser.add_argument("--data-root", type=Path, required=True)
    adjustment_parser.add_argument("--transaction-id", required=True)
    adjustment_parser.add_argument("--actor-id", required=True)
    adjustment_parser.add_argument("--reason", required=True)
    adjustment_parser.add_argument("--journal-json", required=True)
    return parser


def _write_json(stream: TextIO, payload: dict[str, object]) -> None:
    stream.write(json.dumps(payload, sort_keys=True, indent=2))
    stream.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
