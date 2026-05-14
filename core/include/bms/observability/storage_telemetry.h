#ifndef BMS_OBSERVABILITY_STORAGE_TELEMETRY_H
#define BMS_OBSERVABILITY_STORAGE_TELEMETRY_H

#include "bms/observability/logger.h"
#include "bms/observability/metrics.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct BmsStorageTelemetry {
    BmsLogger *logger;
    BmsCounter *storage_records_appended;
    BmsCounter *storage_checksum_failures;
    BmsCounter *storage_duplicate_idempotency_keys;
    BmsCounter *storage_verify_success;
    BmsCounter *wal_pending_appended;
    BmsCounter *wal_committed_appended;
} BmsStorageTelemetry;

#ifdef __cplusplus
}
#endif

#endif
