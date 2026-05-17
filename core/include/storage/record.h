#ifndef BMS_STORAGE_RECORD_H
#define BMS_STORAGE_RECORD_H

#include <stddef.h>

#include "bms/status.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BMS_CHECKSUM_HEX_LEN 64
#define BMS_CHECKSUM_TEXT_LEN 72

typedef struct BmsRecord {
    int schema_version;
    unsigned long long sequence;
    const char *record_id;
    const char *record_type;
    const char *created_at;
    const char *actor_id;
    const char *correlation_id;
    const char *idempotency_key;
    const char *payload_json;
    char checksum[BMS_CHECKSUM_TEXT_LEN];
} BmsRecord;

BmsStatus bms_record_compute_checksum(BmsRecord *record);
BmsStatus bms_record_to_json_line(const BmsRecord *record, char *buffer, size_t buffer_size);
BmsStatus bms_record_verify_json_line(const char *line);
BmsStatus bms_record_extract_idempotency_key(
    const char *line,
    char *buffer,
    size_t buffer_size
);

#ifdef __cplusplus
}
#endif

#endif
