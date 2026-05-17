#ifndef BMS_WAL_WAL_H
#define BMS_WAL_WAL_H

#include "bms/status.h"
#include "bms/observability/storage_telemetry.h"

#ifdef __cplusplus
extern "C" {
#endif

BmsStatus bms_wal_inspect_startup(
    const char *wal_path,
    const char *required_snapshot_path,
    int *recovery_decision
);
BmsStatus bms_wal_inspect_startup_with_telemetry(
    const char *wal_path,
    const char *required_snapshot_path,
    int *recovery_decision,
    const BmsStorageTelemetry *telemetry
);

enum {
    BMS_WAL_RECOVERY_CLEAN = 0,
    BMS_WAL_RECOVERY_PENDING_ROLLBACK = 1,
    BMS_WAL_RECOVERY_COMMITTED_MISSING_SNAPSHOT = 2,
    BMS_WAL_RECOVERY_PROTECTED_READ_ONLY = 3
};

BmsStatus bms_wal_append_pending(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id,
    const char *payload_json
);
BmsStatus bms_wal_append_pending_with_telemetry(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id,
    const char *payload_json,
    const BmsStorageTelemetry *telemetry
);

BmsStatus bms_wal_append_committed(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id
);
BmsStatus bms_wal_append_committed_with_telemetry(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id,
    const BmsStorageTelemetry *telemetry
);

#ifdef __cplusplus
}
#endif

#endif
