#include "bms/storage/record.h"

#include "bms/storage/sha256.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <stdint.h>

static const char *safe_str(const char *value)
{
    return value ? value : "";
}

/* Dynamic string builder helpers */
static BmsStatus ensure_capacity(char **buf, size_t *cap, size_t need)
{
    if (*cap >= need) return BMS_OK;
    size_t newcap = (*cap == 0) ? 1024 : *cap;
    while (newcap < need) newcap *= 2;
    char *n = (char *)realloc(*buf, newcap);
    if (!n) return BMS_ERR_IO;
    *buf = n;
    *cap = newcap;
    return BMS_OK;
}

static BmsStatus append_raw(char **buf, size_t *len, size_t *cap, const char *s)
{
    size_t slen = strlen(s);
    BmsStatus st = ensure_capacity(buf, cap, *len + slen + 1);
    if (st != BMS_OK) return st;
    memcpy(*buf + *len, s, slen);
    *len += slen;
    (*buf)[*len] = '\0';
    return BMS_OK;
}

static BmsStatus append_char(char **buf, size_t *len, size_t *cap, char c)
{
    BmsStatus st = ensure_capacity(buf, cap, *len + 2);
    if (st != BMS_OK) return st;
    (*buf)[(*len)++] = c;
    (*buf)[*len] = '\0';
    return BMS_OK;
}

static void append_hex_u8(char **buf, size_t *len, size_t *cap, uint8_t v)
{
    const char hex[] = "0123456789abcdef";
    ensure_capacity(buf, cap, *len + 5);
    (*buf)[(*len)++] = '\\';
    (*buf)[(*len)++] = 'u';
    (*buf)[(*len)++] = '0';
    (*buf)[(*len)++] = '0';
    (*buf)[(*len)++] = hex[(v >> 4) & 0x0f];
    (*buf)[(*len)++] = hex[v & 0x0f];
    (*buf)[*len] = '\0';
}

static BmsStatus append_quoted_string(char **buf, size_t *len, size_t *cap, const char *s)
{
    BmsStatus st = append_char(buf, len, cap, '"');
    if (st != BMS_OK) return st;

    const unsigned char *p = (const unsigned char *)s;
    while (*p) {
        unsigned char c = *p;
        switch (c) {
            case '"': st = append_raw(buf, len, cap, "\\\""); break;
            case '\\': st = append_raw(buf, len, cap, "\\\\"); break;
            case '\b': st = append_raw(buf, len, cap, "\\b"); break;
            case '\f': st = append_raw(buf, len, cap, "\\f"); break;
            case '\n': st = append_raw(buf, len, cap, "\\n"); break;
            case '\r': st = append_raw(buf, len, cap, "\\r"); break;
            case '\t': st = append_raw(buf, len, cap, "\\t"); break;
            default:
                if (c < 0x20) {
                    append_hex_u8(buf, len, cap, c);
                } else {
                    st = append_char(buf, len, cap, (char)c);
                }
                break;
        }
        if (st != BMS_OK) return st;
        p++;
    }

    return append_char(buf, len, cap, '"');
}

/* Build canonical JSON serialization without the checksum field.
 * Keys are serialized in stable lexicographic order. The payload is
 * inserted raw (it is expected to be valid JSON). The result is a
 * newly allocated NUL-terminated string in *out; caller must free(). */
static BmsStatus build_canonical_json_no_checksum(const BmsRecord *record, char **out, size_t *out_len)
{
    if (!record || !out || !out_len) return BMS_ERR_INVALID_ARGUMENT;
    if (!record->payload_json || record->payload_json[0] == '\0') return BMS_ERR_INVALID_ARGUMENT;

    char *buf = NULL;
    size_t len = 0;
    size_t cap = 0;
    BmsStatus st;

    st = append_char(&buf, &len, &cap, '{');
    if (st != BMS_OK) goto fail;

    /* Order: actor_id, correlation_id, created_at, idempotency_key,
     * payload, record_id, record_type, schema_version, sequence */

    /* actor_id */
    st = append_raw(&buf, &len, &cap, "\"actor_id\":"); if (st != BMS_OK) goto fail;
    st = append_quoted_string(&buf, &len, &cap, safe_str(record->actor_id)); if (st != BMS_OK) goto fail;

    /* correlation_id */
    st = append_raw(&buf, &len, &cap, ",\"correlation_id\":"); if (st != BMS_OK) goto fail;
    st = append_quoted_string(&buf, &len, &cap, safe_str(record->correlation_id)); if (st != BMS_OK) goto fail;

    /* created_at */
    st = append_raw(&buf, &len, &cap, ",\"created_at\":"); if (st != BMS_OK) goto fail;
    st = append_quoted_string(&buf, &len, &cap, safe_str(record->created_at)); if (st != BMS_OK) goto fail;

    /* idempotency_key */
    st = append_raw(&buf, &len, &cap, ",\"idempotency_key\":"); if (st != BMS_OK) goto fail;
    st = append_quoted_string(&buf, &len, &cap, safe_str(record->idempotency_key)); if (st != BMS_OK) goto fail;

    /* payload (raw JSON) */
    st = append_raw(&buf, &len, &cap, ",\"payload\":"); if (st != BMS_OK) goto fail;
    st = append_raw(&buf, &len, &cap, record->payload_json); if (st != BMS_OK) goto fail;

    /* record_id */
    st = append_raw(&buf, &len, &cap, ",\"record_id\":"); if (st != BMS_OK) goto fail;
    st = append_quoted_string(&buf, &len, &cap, safe_str(record->record_id)); if (st != BMS_OK) goto fail;

    /* record_type */
    st = append_raw(&buf, &len, &cap, ",\"record_type\":"); if (st != BMS_OK) goto fail;
    st = append_quoted_string(&buf, &len, &cap, safe_str(record->record_type)); if (st != BMS_OK) goto fail;

    /* schema_version */
    char tmp[64];
    int n = snprintf(tmp, sizeof(tmp), ",\"schema_version\":%d", record->schema_version);
    if (n < 0 || n >= (int)sizeof(tmp)) { st = BMS_ERR_BUFFER_TOO_SMALL; goto fail; }
    st = append_raw(&buf, &len, &cap, tmp); if (st != BMS_OK) goto fail;

    /* sequence */
    n = snprintf(tmp, sizeof(tmp), ",\"sequence\":%llu", record->sequence);
    if (n < 0 || n >= (int)sizeof(tmp)) { st = BMS_ERR_BUFFER_TOO_SMALL; goto fail; }
    st = append_raw(&buf, &len, &cap, tmp); if (st != BMS_OK) goto fail;

    st = append_char(&buf, &len, &cap, '}'); if (st != BMS_OK) goto fail;

    *out = buf;
    *out_len = len;
    return BMS_OK;

fail:
    free(buf);
    return st;
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
    char hex[65];
    char *canonical = NULL;
    size_t canonical_len = 0;
    BmsStatus status;

    if (!record) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    status = build_canonical_json_no_checksum(record, &canonical, &canonical_len);
    if (status != BMS_OK) {
        return status;
    }

    bms_sha256_hex((const unsigned char *)canonical, canonical_len, hex);
    if (snprintf(record->checksum, sizeof(record->checksum), "sha256:%s", hex) >= (int)sizeof(record->checksum)) {
        free(canonical);
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    free(canonical);
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
