#include "bms/wal/wal.h"

#include "bms/observability/logger.h"
#include "bms/observability/metrics.h"
#include "bms/storage/jsonl_store.h"

#include <stdio.h>
#include <string.h>

static BmsStatus append_wal_record(
    const char *wal_path,
    const char *transaction_id,
    const char *state,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id,
    const char *payload_json,
    const BmsStorageTelemetry *telemetry)
{
    char record_id[256];
    char idempotency_key[256];
    char payload[4096];
    BmsRecord record;

    if (!wal_path || !transaction_id || !state || !created_at || !actor_id || !correlation_id)
    {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    if (snprintf(record_id, sizeof(record_id), "wal_%s_%s", transaction_id, state) >= (int)sizeof(record_id))
    {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }
    if (snprintf(idempotency_key, sizeof(idempotency_key), "wal_%s_%s", transaction_id, state) >= (int)sizeof(idempotency_key))
    {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }
    if (snprintf(
            payload,
            sizeof(payload),
            "{\"transaction_id\":\"%s\",\"state\":\"%s\",\"payload\":%s}",
            transaction_id,
            state,
            payload_json ? payload_json : "{}") >= (int)sizeof(payload))
    {
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

    return bms_jsonl_append_record_with_telemetry(wal_path, &record, telemetry);
}

BmsStatus bms_wal_append_pending(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id,
    const char *payload_json)
{
    return bms_wal_append_pending_with_telemetry(
        wal_path,
        transaction_id,
        created_at,
        actor_id,
        correlation_id,
        payload_json,
        NULL);
}

BmsStatus bms_wal_append_pending_with_telemetry(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id,
    const char *payload_json,
    const BmsStorageTelemetry *telemetry)
{
    BmsStatus status = append_wal_record(
        wal_path,
        transaction_id,
        "pending",
        created_at,
        actor_id,
        correlation_id,
        payload_json ? payload_json : "{}",
        telemetry);
    if (status == BMS_OK)
    {
        if (telemetry && telemetry->wal_pending_appended)
        {
            (void)bms_counter_inc(telemetry->wal_pending_appended, 1);
        }
        if (telemetry && telemetry->logger)
        {
            (void)bms_logger_write(
                telemetry->logger,
                BMS_LOG_INFO,
                "2026-05-14T00:00:00Z",
                "wal",
                correlation_id ? correlation_id : "n/a",
                "wal pending appended");
        }
    }
    return status;
}

BmsStatus bms_wal_append_committed(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id)
{
    return bms_wal_append_committed_with_telemetry(
        wal_path,
        transaction_id,
        created_at,
        actor_id,
        correlation_id,
        NULL);
}

BmsStatus bms_wal_append_committed_with_telemetry(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id,
    const BmsStorageTelemetry *telemetry)
{
    BmsStatus status = append_wal_record(
        wal_path,
        transaction_id,
        "committed",
        created_at,
        actor_id,
        correlation_id,
        "{}",
        telemetry);
    if (status == BMS_OK)
    {
        if (telemetry && telemetry->wal_committed_appended)
        {
            (void)bms_counter_inc(telemetry->wal_committed_appended, 1);
        }
        if (telemetry && telemetry->logger)
        {
            (void)bms_logger_write(
                telemetry->logger,
                BMS_LOG_INFO,
                "2026-05-14T00:00:00Z",
                "wal",
                correlation_id ? correlation_id : "n/a",
                "wal committed appended");
        }
    }
    return status;
}

static void wal_log(
    const BmsStorageTelemetry *telemetry,
    BmsLogLevel level,
    const char *correlation_id,
    const char *message)
{
    if (!telemetry || !telemetry->logger)
    {
        return;
    }
    (void)bms_logger_write(
        telemetry->logger,
        level,
        "2026-05-14T00:00:00Z",
        "wal",
        correlation_id ? correlation_id : "n/a",
        message);
}

static int file_exists(const char *path)
{
    FILE *file;
    if (!path)
    {
        return 0;
    }
    file = fopen(path, "r");
    if (!file)
    {
        return 0;
    }
    fclose(file);
    return 1;
}

BmsStatus bms_wal_inspect_startup(
    const char *wal_path,
    const char *required_snapshot_path,
    int *recovery_decision)
{
    return bms_wal_inspect_startup_with_telemetry(
        wal_path,
        required_snapshot_path,
        recovery_decision,
        NULL);
}

BmsStatus bms_wal_inspect_startup_with_telemetry(
    const char *wal_path,
    const char *required_snapshot_path,
    int *recovery_decision,
    const BmsStorageTelemetry *telemetry)
{
    FILE *file;
    char line[8192];
    unsigned long long valid_records = 0;
    unsigned long long pending_count = 0;
    unsigned long long committed_count = 0;
    BmsStatus status;

    if (!wal_path || !recovery_decision)
    {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    *recovery_decision = BMS_WAL_RECOVERY_CLEAN;

    status = bms_jsonl_verify_file(wal_path, &valid_records);
    if (status == BMS_ERR_CHECKSUM || status == BMS_ERR_PARSE)
    {
        *recovery_decision = BMS_WAL_RECOVERY_PROTECTED_READ_ONLY;
        wal_log(telemetry, BMS_LOG_ERROR, "n/a", "protected read-only mode entered");
        return BMS_ERR_PROTECTED_MODE;
    }
    if (status != BMS_OK)
    {
        return status;
    }
    if (valid_records == 0)
    {
        wal_log(telemetry, BMS_LOG_INFO, "n/a", "wal recovery clean");
        return BMS_OK;
    }

    file = fopen(wal_path, "r");
    if (!file)
    {
        return BMS_ERR_IO;
    }
    while (fgets(line, sizeof(line), file))
    {
        if (strstr(line, "\"state\":\"pending\""))
        {
            pending_count++;
        }
        if (strstr(line, "\"state\":\"committed\""))
        {
            committed_count++;
        }
    }
    fclose(file);

    if (pending_count > committed_count)
    {
        *recovery_decision = BMS_WAL_RECOVERY_PENDING_ROLLBACK;
        wal_log(telemetry, BMS_LOG_WARN, "n/a", "pending wal requires rollback decision");
        return BMS_ERR_RECOVERY_REQUIRED;
    }

    if (committed_count > 0 && required_snapshot_path && !file_exists(required_snapshot_path))
    {
        *recovery_decision = BMS_WAL_RECOVERY_COMMITTED_MISSING_SNAPSHOT;
        wal_log(telemetry, BMS_LOG_WARN, "n/a", "committed wal missing snapshot");
        return BMS_ERR_RECOVERY_REQUIRED;
    }

    wal_log(telemetry, BMS_LOG_INFO, "n/a", "wal recovery clean");
    return BMS_OK;
}
