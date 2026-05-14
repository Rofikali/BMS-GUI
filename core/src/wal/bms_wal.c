#include "bms/wal/wal.h"

#include "bms/storage/jsonl_store.h"

#include <stdio.h>

static BmsStatus append_wal_record(
    const char *wal_path,
    const char *transaction_id,
    const char *state,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id,
    const char *payload_json
)
{
    char record_id[256];
    char idempotency_key[256];
    char payload[4096];
    BmsRecord record;

    if (!wal_path || !transaction_id || !state || !created_at || !actor_id || !correlation_id) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    if (snprintf(record_id, sizeof(record_id), "wal_%s_%s", transaction_id, state) >= (int)sizeof(record_id)) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }
    if (snprintf(idempotency_key, sizeof(idempotency_key), "wal_%s_%s", transaction_id, state) >= (int)sizeof(idempotency_key)) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }
    if (snprintf(
            payload,
            sizeof(payload),
            "{\"transaction_id\":\"%s\",\"state\":\"%s\",\"payload\":%s}",
            transaction_id,
            state,
            payload_json ? payload_json : "{}") >= (int)sizeof(payload)) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    record.schema_version = 1;
    record.sequence = 0;
    record.record_id = record_id;
    record.record_type = "wal.transaction";
    record.created_at = created_at;
    record.actor_id = actor_id;
    record.correlation_id = correlation_id;
    record.idempotency_key = idempotency_key;
    record.payload_json = payload;
    record.checksum[0] = '\0';

    return bms_jsonl_append_record(wal_path, &record);
}

BmsStatus bms_wal_append_pending(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id,
    const char *payload_json
)
{
    return append_wal_record(
        wal_path,
        transaction_id,
        "pending",
        created_at,
        actor_id,
        correlation_id,
        payload_json ? payload_json : "{}");
}

BmsStatus bms_wal_append_committed(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id
)
{
    return append_wal_record(
        wal_path,
        transaction_id,
        "committed",
        created_at,
        actor_id,
        correlation_id,
        "{}");
}
