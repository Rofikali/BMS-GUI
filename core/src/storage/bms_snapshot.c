#define _POSIX_C_SOURCE 200809L

#include "bms/storage/snapshot.h"

#include "bms/storage/sha256.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#include <io.h>
#define bms_fsync _commit
#else
#include <unistd.h>
#define bms_fsync fsync
#endif

static BmsStatus build_snapshot_without_checksum(
    char *buffer,
    size_t buffer_size,
    int schema_version,
    const char *generated_at,
    const char *source_files_json,
    unsigned long long last_applied_sequence,
    const char *payload_json)
{
    int written;
    if (!buffer || !generated_at || !source_files_json || !payload_json) {
        return BMS_ERR_INVALID_ARGUMENT;
    }
    written = snprintf(
        buffer,
        buffer_size,
        "{\"generated_at\":\"%s\",\"last_applied_sequence\":%llu,\"payload\":%s,\"schema_version\":%d,\"source_files\":%s}",
        generated_at,
        last_applied_sequence,
        payload_json,
        schema_version,
        source_files_json);
    return (written > 0 && (size_t)written < buffer_size) ? BMS_OK : BMS_ERR_BUFFER_TOO_SMALL;
}

static BmsStatus build_snapshot_with_checksum(
    char *buffer,
    size_t buffer_size,
    const char *without_checksum,
    const char *checksum)
{
    size_t len;
    int written;
    if (!buffer || !without_checksum || !checksum) {
        return BMS_ERR_INVALID_ARGUMENT;
    }
    len = strlen(without_checksum);
    if (len == 0 || without_checksum[len - 1] != '}') {
        return BMS_ERR_PARSE;
    }
    written = snprintf(
        buffer,
        buffer_size,
        "%.*s,\"checksum\":\"%s\"}\n",
        (int)(len - 1),
        without_checksum,
        checksum);
    return (written > 0 && (size_t)written < buffer_size) ? BMS_OK : BMS_ERR_BUFFER_TOO_SMALL;
}

static BmsStatus checksum_snapshot(const char *without_checksum, char *checksum, size_t checksum_size)
{
    char hex[65];
    if (!without_checksum || !checksum || checksum_size < 72) {
        return BMS_ERR_INVALID_ARGUMENT;
    }
    bms_sha256_hex((const unsigned char *)without_checksum, strlen(without_checksum), hex);
    if (snprintf(checksum, checksum_size, "sha256:%s", hex) >= (int)checksum_size) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }
    return BMS_OK;
}

static BmsStatus flush_file(FILE *file)
{
    if (fflush(file) != 0) return BMS_ERR_IO;
    if (bms_fsync(fileno(file)) != 0) return BMS_ERR_IO;
    return BMS_OK;
}

BmsStatus bms_snapshot_write_atomic(
    const char *path,
    int schema_version,
    const char *generated_at,
    const char *source_files_json,
    unsigned long long last_applied_sequence,
    const char *payload_json)
{
    char without_checksum[8192];
    char checksum[72];
    char final_json[9000];
    char temp_path[1024];
    FILE *file;
    BmsStatus status;

    if (!path) {
        return BMS_ERR_INVALID_ARGUMENT;
    }
    if (snprintf(temp_path, sizeof(temp_path), "%s.tmp", path) >= (int)sizeof(temp_path)) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    status = build_snapshot_without_checksum(
        without_checksum,
        sizeof(without_checksum),
        schema_version,
        generated_at,
        source_files_json,
        last_applied_sequence,
        payload_json);
    if (status != BMS_OK) return status;
    status = checksum_snapshot(without_checksum, checksum, sizeof(checksum));
    if (status != BMS_OK) return status;
    status = build_snapshot_with_checksum(final_json, sizeof(final_json), without_checksum, checksum);
    if (status != BMS_OK) return status;

    file = fopen(temp_path, "w");
    if (!file) return BMS_ERR_IO;
    if (fputs(final_json, file) == EOF) {
        fclose(file);
        return BMS_ERR_IO;
    }
    status = flush_file(file);
    fclose(file);
    if (status != BMS_OK) return status;
    if (rename(temp_path, path) != 0) return BMS_ERR_IO;
    return BMS_OK;
}

BmsStatus bms_snapshot_verify_file(const char *path)
{
    FILE *file;
    char line[9000];
    char without_checksum[8192];
    char expected[72];
    char *checksum_field;
    char *checksum_start;
    char *checksum_end;
    size_t prefix_len;
    BmsStatus status;

    if (!path) return BMS_ERR_INVALID_ARGUMENT;
    file = fopen(path, "r");
    if (!file) return BMS_ERR_IO;
    if (!fgets(line, sizeof(line), file)) {
        fclose(file);
        return BMS_ERR_PARSE;
    }
    fclose(file);

    checksum_field = strstr(line, ",\"checksum\":\"");
    if (!checksum_field) return BMS_ERR_PARSE;
    prefix_len = (size_t)(checksum_field - line);
    if (prefix_len + 2 > sizeof(without_checksum)) return BMS_ERR_BUFFER_TOO_SMALL;
    memcpy(without_checksum, line, prefix_len);
    without_checksum[prefix_len] = '}';
    without_checksum[prefix_len + 1] = '\0';

    checksum_start = checksum_field + strlen(",\"checksum\":\"");
    checksum_end = strchr(checksum_start, '"');
    if (!checksum_end) return BMS_ERR_PARSE;
    *checksum_end = '\0';

    status = checksum_snapshot(without_checksum, expected, sizeof(expected));
    if (status != BMS_OK) return status;
    return strcmp(expected, checksum_start) == 0 ? BMS_OK : BMS_ERR_CHECKSUM;
}
