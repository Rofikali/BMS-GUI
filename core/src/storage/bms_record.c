#include "bms/storage/record.h"

#include "bms/storage/sha256.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *safe_str(const char *value)
{
    return value ? value : "";
}

static BmsStatus canonical_record_string(const BmsRecord *record, char *buffer, size_t buffer_size)
{
    int written;

    if (!record || !buffer || buffer_size == 0) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    written = snprintf(
        buffer,
        buffer_size,
        "schema_version=%d\nsequence=%llu\nrecord_id=%s\nrecord_type=%s\ncreated_at=%s\nactor_id=%s\ncorrelation_id=%s\nidempotency_key=%s\npayload=%s\n",
        record->schema_version,
        record->sequence,
        safe_str(record->record_id),
        safe_str(record->record_type),
        safe_str(record->created_at),
        safe_str(record->actor_id),
        safe_str(record->correlation_id),
        safe_str(record->idempotency_key),
        safe_str(record->payload_json));

    if (written < 0 || (size_t)written >= buffer_size) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    return BMS_OK;
}

static BmsStatus extract_json_string(const char *line, const char *field, char *buffer, size_t buffer_size)
{
    char pattern[96];
    const char *start;
    const char *end;
    size_t len;

    if (!line || !field || !buffer || buffer_size == 0) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    if (snprintf(pattern, sizeof(pattern), "\"%s\":\"", field) >= (int)sizeof(pattern)) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    start = strstr(line, pattern);
    if (!start) {
        return BMS_ERR_PARSE;
    }
    start += strlen(pattern);
    end = strchr(start, '"');
    if (!end) {
        return BMS_ERR_PARSE;
    }

    len = (size_t)(end - start);
    if (len + 1 > buffer_size) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    memcpy(buffer, start, len);
    buffer[len] = '\0';
    return BMS_OK;
}

static BmsStatus extract_json_payload(const char *line, char *buffer, size_t buffer_size)
{
    const char *pattern = "\"payload\":";
    const char *start;
    const char *end;
    size_t len;

    if (!line || !buffer || buffer_size == 0) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    start = strstr(line, pattern);
    if (!start) {
        return BMS_ERR_PARSE;
    }
    start += strlen(pattern);
    end = strstr(start, ",\"checksum\":\"");
    if (!end) {
        return BMS_ERR_PARSE;
    }

    len = (size_t)(end - start);
    if (len + 1 > buffer_size) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    memcpy(buffer, start, len);
    buffer[len] = '\0';
    return BMS_OK;
}

static BmsStatus extract_json_int(const char *line, const char *field, int *value)
{
    char pattern[96];
    const char *start;

    if (!line || !field || !value) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    if (snprintf(pattern, sizeof(pattern), "\"%s\":", field) >= (int)sizeof(pattern)) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    start = strstr(line, pattern);
    if (!start) {
        return BMS_ERR_PARSE;
    }
    start += strlen(pattern);
    *value = atoi(start);
    return BMS_OK;
}

static BmsStatus extract_json_ull(const char *line, const char *field, unsigned long long *value)
{
    char pattern[96];
    const char *start;

    if (!line || !field || !value) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    if (snprintf(pattern, sizeof(pattern), "\"%s\":", field) >= (int)sizeof(pattern)) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    start = strstr(line, pattern);
    if (!start) {
        return BMS_ERR_PARSE;
    }
    start += strlen(pattern);
    *value = strtoull(start, NULL, 10);
    return BMS_OK;
}

BmsStatus bms_record_compute_checksum(BmsRecord *record)
{
    char canonical[8192];
    char hex[65];
    BmsStatus status;

    if (!record) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    status = canonical_record_string(record, canonical, sizeof(canonical));
    if (status != BMS_OK) {
        return status;
    }

    bms_sha256_hex((const unsigned char *)canonical, strlen(canonical), hex);
    if (snprintf(record->checksum, sizeof(record->checksum), "sha256:%s", hex) >= (int)sizeof(record->checksum)) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    return BMS_OK;
}

BmsStatus bms_record_to_json_line(const BmsRecord *record, char *buffer, size_t buffer_size)
{
    int written;

    if (!record || !buffer || buffer_size == 0) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    if (!record->payload_json || record->payload_json[0] == '\0') {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    written = snprintf(
        buffer,
        buffer_size,
        "{\"schema_version\":%d,\"sequence\":%llu,\"record_id\":\"%s\",\"record_type\":\"%s\",\"created_at\":\"%s\",\"actor_id\":\"%s\",\"correlation_id\":\"%s\",\"idempotency_key\":\"%s\",\"payload\":%s,\"checksum\":\"%s\"}\n",
        record->schema_version,
        record->sequence,
        safe_str(record->record_id),
        safe_str(record->record_type),
        safe_str(record->created_at),
        safe_str(record->actor_id),
        safe_str(record->correlation_id),
        safe_str(record->idempotency_key),
        record->payload_json,
        safe_str(record->checksum));

    if (written < 0 || (size_t)written >= buffer_size) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    return BMS_OK;
}

BmsStatus bms_record_extract_idempotency_key(const char *line, char *buffer, size_t buffer_size)
{
    return extract_json_string(line, "idempotency_key", buffer, buffer_size);
}

BmsStatus bms_record_verify_json_line(const char *line)
{
    BmsRecord record;
    char record_id[256];
    char record_type[256];
    char created_at[128];
    char actor_id[256];
    char correlation_id[256];
    char idempotency_key[256];
    char payload[4096];
    char checksum[BMS_CHECKSUM_TEXT_LEN];
    BmsStatus status;

    if (!line) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    memset(&record, 0, sizeof(record));
    status = extract_json_int(line, "schema_version", &record.schema_version);
    if (status != BMS_OK) return status;
    status = extract_json_ull(line, "sequence", &record.sequence);
    if (status != BMS_OK) return status;
    status = extract_json_string(line, "record_id", record_id, sizeof(record_id));
    if (status != BMS_OK) return status;
    status = extract_json_string(line, "record_type", record_type, sizeof(record_type));
    if (status != BMS_OK) return status;
    status = extract_json_string(line, "created_at", created_at, sizeof(created_at));
    if (status != BMS_OK) return status;
    status = extract_json_string(line, "actor_id", actor_id, sizeof(actor_id));
    if (status != BMS_OK) return status;
    status = extract_json_string(line, "correlation_id", correlation_id, sizeof(correlation_id));
    if (status != BMS_OK) return status;
    status = extract_json_string(line, "idempotency_key", idempotency_key, sizeof(idempotency_key));
    if (status != BMS_OK) return status;
    status = extract_json_payload(line, payload, sizeof(payload));
    if (status != BMS_OK) return status;
    status = extract_json_string(line, "checksum", checksum, sizeof(checksum));
    if (status != BMS_OK) return status;

    record.record_id = record_id;
    record.record_type = record_type;
    record.created_at = created_at;
    record.actor_id = actor_id;
    record.correlation_id = correlation_id;
    record.idempotency_key = idempotency_key;
    record.payload_json = payload;

    status = bms_record_compute_checksum(&record);
    if (status != BMS_OK) {
        return status;
    }

    return strcmp(record.checksum, checksum) == 0 ? BMS_OK : BMS_ERR_CHECKSUM;
}
