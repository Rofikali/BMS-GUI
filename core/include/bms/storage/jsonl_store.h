#ifndef BMS_STORAGE_JSONL_STORE_H
#define BMS_STORAGE_JSONL_STORE_H

#include "bms/status.h"
#include "bms/observability/storage_telemetry.h"
#include "bms/storage/record.h"

#ifdef __cplusplus
extern "C" {
#endif

BmsStatus bms_jsonl_append_record(const char *path, BmsRecord *record);
BmsStatus bms_jsonl_append_record_with_telemetry(
    const char *path,
    BmsRecord *record,
    const BmsStorageTelemetry *telemetry
);
BmsStatus bms_jsonl_verify_file(const char *path, unsigned long long *valid_records);
BmsStatus bms_jsonl_verify_file_with_telemetry(
    const char *path,
    unsigned long long *valid_records,
    const BmsStorageTelemetry *telemetry
);
BmsStatus bms_jsonl_next_sequence(const char *path, unsigned long long *next_sequence);
BmsStatus bms_jsonl_contains_idempotency_key(
    const char *path,
    const char *idempotency_key,
    int *contains_key
);

#ifdef __cplusplus
}
#endif

#endif
