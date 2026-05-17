#ifndef BMS_STORAGE_SNAPSHOT_H
#define BMS_STORAGE_SNAPSHOT_H

#include "bms/status.h"

#ifdef __cplusplus
extern "C" {
#endif

BmsStatus bms_snapshot_write_atomic(
    const char *path,
    int schema_version,
    const char *generated_at,
    const char *source_files_json,
    unsigned long long last_applied_sequence,
    const char *payload_json
);
BmsStatus bms_snapshot_verify_file(const char *path);

#ifdef __cplusplus
}
#endif

#endif
