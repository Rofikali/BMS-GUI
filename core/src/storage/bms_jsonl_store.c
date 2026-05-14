#define _POSIX_C_SOURCE 200809L

#include "bms/storage/jsonl_store.h"

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
    FILE *file;
    char line[8192];
    int contains_key = 0;
    BmsStatus status;

    if (!path || !record || !record->idempotency_key) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    status = bms_jsonl_contains_idempotency_key(path, record->idempotency_key, &contains_key);
    if (status != BMS_OK) {
        return status;
    }
    if (contains_key) {
        return BMS_ERR_DUPLICATE_IDEMPOTENCY_KEY;
    }

    status = bms_jsonl_next_sequence(path, &record->sequence);
    if (status != BMS_OK) {
        return status;
    }

    status = bms_record_compute_checksum(record);
    if (status != BMS_OK) {
        return status;
    }

    status = bms_record_to_json_line(record, line, sizeof(line));
    if (status != BMS_OK) {
        return status;
    }

    file = fopen(path, "a");
    if (!file) {
        return BMS_ERR_IO;
    }

    if (fputs(line, file) == EOF) {
        fclose(file);
        return BMS_ERR_IO;
    }

    status = flush_file(file);
    fclose(file);
    return status;
}

BmsStatus bms_jsonl_verify_file(const char *path, unsigned long long *valid_records)
{
    FILE *file;
    char line[8192];
    unsigned long long count = 0;
    BmsStatus status;

    if (!path) {
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
            return status;
        }
        count++;
    }

    fclose(file);
    if (valid_records) {
        *valid_records = count;
    }
    return BMS_OK;
}
