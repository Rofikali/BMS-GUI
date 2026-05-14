#define _POSIX_C_SOURCE 200809L

#include "bms/storage/jsonl_store.h"

#include "bms/observability/logger.h"
#include "bms/observability/metrics.h"

#include <stdio.h>
#include <string.h>

#if defined(_WIN32)
#include <io.h>
#define bms_fsync _commit
#else
#include <unistd.h>
#define bms_fsync fsync
#endif

static BmsStatus flush_file(FILE *file)
{
    if (fflush(file) != 0) {
        return BMS_ERR_IO;
    }
    if (bms_fsync(fileno(file)) != 0) {
        return BMS_ERR_IO;
    }
    return BMS_OK;
}

static void telemetry_log(
    const BmsStorageTelemetry *telemetry,
    BmsLogLevel level,
    const char *module,
    const char *correlation_id,
    const char *message
)
{
    if (!telemetry || !telemetry->logger) {
        return;
    }
    (void)bms_logger_write(
        telemetry->logger,
        level,
        "2026-05-14T00:00:00Z",
        module,
        correlation_id ? correlation_id : "n/a",
        message);
}

static void telemetry_inc(BmsCounter *counter)
{
    if (!counter) {
        return;
    }
    (void)bms_counter_inc(counter, 1);
}

BmsStatus bms_jsonl_next_sequence(const char *path, unsigned long long *next_sequence)
{
    FILE *file;
    char line[8192];
    unsigned long long count = 1;

    if (!path || !next_sequence) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    file = fopen(path, "r");
    if (!file) {
        *next_sequence = 1;
        return BMS_OK;
    }

    while (fgets(line, sizeof(line), file)) {
        count++;
    }

    fclose(file);
    *next_sequence = count;
    return BMS_OK;
}

BmsStatus bms_jsonl_contains_idempotency_key(
    const char *path,
    const char *idempotency_key,
    int *contains_key
)
{
    FILE *file;
    char line[8192];
    char existing_key[256];

    if (!path || !idempotency_key || !contains_key) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    *contains_key = 0;
    file = fopen(path, "r");
    if (!file) {
        return BMS_OK;
    }

    while (fgets(line, sizeof(line), file)) {
        if (bms_record_extract_idempotency_key(line, existing_key, sizeof(existing_key)) == BMS_OK &&
            strcmp(existing_key, idempotency_key) == 0) {
            *contains_key = 1;
            fclose(file);
            return BMS_OK;
        }
    }

    fclose(file);
    return BMS_OK;
}

BmsStatus bms_jsonl_append_record(const char *path, BmsRecord *record)
{
    return bms_jsonl_append_record_with_telemetry(path, record, NULL);
}

BmsStatus bms_jsonl_append_record_with_telemetry(
    const char *path,
    BmsRecord *record,
    const BmsStorageTelemetry *telemetry
)
{
    FILE *file;
    char line[8192];
    int contains_key = 0;
    BmsStatus status;

    if (!path || !record || !record->idempotency_key) {
        telemetry_log(telemetry, BMS_LOG_ERROR, "storage", "n/a", "append invalid argument");
        return BMS_ERR_INVALID_ARGUMENT;
    }

    status = bms_jsonl_contains_idempotency_key(path, record->idempotency_key, &contains_key);
    if (status != BMS_OK) {
        telemetry_log(telemetry, BMS_LOG_ERROR, "storage", record->correlation_id, "idempotency scan failed");
        return status;
    }
    if (contains_key) {
        telemetry_inc(telemetry ? telemetry->storage_duplicate_idempotency_keys : NULL);
        telemetry_log(telemetry, BMS_LOG_WARN, "storage", record->correlation_id, "duplicate idempotency key rejected");
        return BMS_ERR_DUPLICATE_IDEMPOTENCY_KEY;
    }

    status = bms_jsonl_next_sequence(path, &record->sequence);
    if (status != BMS_OK) {
        telemetry_log(telemetry, BMS_LOG_ERROR, "storage", record->correlation_id, "next sequence read failed");
        return status;
    }

    status = bms_record_compute_checksum(record);
    if (status != BMS_OK) {
        telemetry_log(telemetry, BMS_LOG_ERROR, "storage", record->correlation_id, "checksum compute failed");
        return status;
    }

    status = bms_record_to_json_line(record, line, sizeof(line));
    if (status != BMS_OK) {
        telemetry_log(telemetry, BMS_LOG_ERROR, "storage", record->correlation_id, "json serialization failed");
        return status;
    }

    file = fopen(path, "a");
    if (!file) {
        telemetry_log(telemetry, BMS_LOG_ERROR, "storage", record->correlation_id, "open append file failed");
        return BMS_ERR_IO;
    }

    if (fputs(line, file) == EOF) {
        fclose(file);
        telemetry_log(telemetry, BMS_LOG_ERROR, "storage", record->correlation_id, "write append file failed");
        return BMS_ERR_IO;
    }

    status = flush_file(file);
    fclose(file);
    if (status == BMS_OK) {
        telemetry_inc(telemetry ? telemetry->storage_records_appended : NULL);
        telemetry_log(telemetry, BMS_LOG_INFO, "storage", record->correlation_id, "record appended");
    } else {
        telemetry_log(telemetry, BMS_LOG_ERROR, "storage", record->correlation_id, "flush append file failed");
    }
    return status;
}

BmsStatus bms_jsonl_verify_file(const char *path, unsigned long long *valid_records)
{
    return bms_jsonl_verify_file_with_telemetry(path, valid_records, NULL);
}

BmsStatus bms_jsonl_verify_file_with_telemetry(
    const char *path,
    unsigned long long *valid_records,
    const BmsStorageTelemetry *telemetry
)
{
    FILE *file;
    char line[8192];
    unsigned long long count = 0;
    BmsStatus status;

    if (!path) {
        telemetry_log(telemetry, BMS_LOG_ERROR, "storage", "n/a", "verify invalid argument");
        return BMS_ERR_INVALID_ARGUMENT;
    }

    file = fopen(path, "r");
    if (!file) {
        if (valid_records) {
            *valid_records = 0;
        }
        return BMS_OK;
    }

    while (fgets(line, sizeof(line), file)) {
        status = bms_record_verify_json_line(line);
        if (status != BMS_OK) {
            fclose(file);
            if (status == BMS_ERR_CHECKSUM) {
                telemetry_inc(telemetry ? telemetry->storage_checksum_failures : NULL);
                telemetry_log(telemetry, BMS_LOG_ERROR, "storage", "n/a", "checksum verification failed");
            }
            return status;
        }
        count++;
    }

    fclose(file);
    if (valid_records) {
        *valid_records = count;
    }
    telemetry_inc(telemetry ? telemetry->storage_verify_success : NULL);
    telemetry_log(telemetry, BMS_LOG_INFO, "storage", "n/a", "verify file success");
    return BMS_OK;
}
