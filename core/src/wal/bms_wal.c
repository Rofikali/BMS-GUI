#define _POSIX_C_SOURCE 200809L

#include "bms/wal/wal.h"

#include "bms/observability/logger.h"
#include "bms/observability/metrics.h"
#include "bms/storage/jsonl_store.h"

#include <stdio.h>
#include <string.h>

#if defined(_WIN32)
#include <io.h>
#include <windows.h>
#define bms_fsync _commit
#else
#include <unistd.h>
#define bms_fsync fsync
#endif

#define BMS_WAL_MAX_TRANSACTIONS 512
#define BMS_WAL_ID_SIZE 256

typedef struct BmsWalTransactionState {
    char transaction_id[BMS_WAL_ID_SIZE];
    int has_pending;
    int has_committed;
} BmsWalTransactionState;

static BmsStatus flush_file(FILE *file)
{
    if (fflush(file) != 0)
    {
        return BMS_ERR_IO;
    }
    if (bms_fsync(fileno(file)) != 0)
    {
        return BMS_ERR_IO;
    }
    return BMS_OK;
}

static BmsStatus replace_file(const char *source_path, const char *target_path)
{
#if defined(_WIN32)
    if (!MoveFileExA(source_path, target_path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
    {
        return BMS_ERR_IO;
    }
    return BMS_OK;
#else
    if (rename(source_path, target_path) != 0)
    {
        return BMS_ERR_IO;
    }
    return BMS_OK;
#endif
}

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

static BmsStatus extract_json_string(const char *line, const char *key, char *out, size_t out_size)
{
    char pattern[64];
    const char *start;
    const char *end;
    size_t length;

    if (!line || !key || !out || out_size == 0)
    {
        return BMS_ERR_INVALID_ARGUMENT;
    }
    if (snprintf(pattern, sizeof(pattern), "\"%s\":\"", key) >= (int)sizeof(pattern))
    {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    start = strstr(line, pattern);
    if (!start)
    {
        return BMS_ERR_PARSE;
    }
    start += strlen(pattern);
    end = strchr(start, '"');
    if (!end)
    {
        return BMS_ERR_PARSE;
    }

    length = (size_t)(end - start);
    if (length >= out_size)
    {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }
    memcpy(out, start, length);
    out[length] = '\0';
    return BMS_OK;
}

static int find_transaction(
    const BmsWalTransactionState *transactions,
    size_t count,
    const char *transaction_id)
{
    size_t index;
    for (index = 0; index < count; index++)
    {
        if (strcmp(transactions[index].transaction_id, transaction_id) == 0)
        {
            return (int)index;
        }
    }
    return -1;
}

static BmsStatus find_or_add_transaction(
    BmsWalTransactionState *transactions,
    size_t *count,
    const char *transaction_id,
    BmsWalTransactionState **transaction)
{
    int existing;

    existing = find_transaction(transactions, *count, transaction_id);
    if (existing >= 0)
    {
        *transaction = &transactions[existing];
        return BMS_OK;
    }
    if (*count >= BMS_WAL_MAX_TRANSACTIONS)
    {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }
    if (strlen(transaction_id) >= sizeof(transactions[*count].transaction_id))
    {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    strcpy(transactions[*count].transaction_id, transaction_id);
    transactions[*count].has_pending = 0;
    transactions[*count].has_committed = 0;
    *transaction = &transactions[*count];
    *count += 1;
    return BMS_OK;
}

static BmsStatus scan_wal_transactions(
    const char *wal_path,
    BmsWalTransactionState *transactions,
    size_t *transaction_count)
{
    FILE *file;
    char line[8192];
    char transaction_id[BMS_WAL_ID_SIZE];
    char state[32];
    BmsWalTransactionState *transaction;
    BmsStatus status;

    if (!wal_path || !transactions || !transaction_count)
    {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    *transaction_count = 0;
    file = fopen(wal_path, "r");
    if (!file)
    {
        return BMS_OK;
    }

    while (fgets(line, sizeof(line), file))
    {
        status = extract_json_string(line, "transaction_id", transaction_id, sizeof(transaction_id));
        if (status != BMS_OK)
        {
            fclose(file);
            return status;
        }
        status = extract_json_string(line, "state", state, sizeof(state));
        if (status != BMS_OK)
        {
            fclose(file);
            return status;
        }
        status = find_or_add_transaction(transactions, transaction_count, transaction_id, &transaction);
        if (status != BMS_OK)
        {
            fclose(file);
            return status;
        }

        if (strcmp(state, "pending") == 0)
        {
            transaction->has_pending = 1;
        }
        else if (strcmp(state, "committed") == 0)
        {
            transaction->has_committed = 1;
        }
    }

    fclose(file);
    return BMS_OK;
}

static int wal_has_uncommitted_pending(const BmsWalTransactionState *transactions, size_t transaction_count)
{
    size_t index;
    for (index = 0; index < transaction_count; index++)
    {
        if (transactions[index].has_pending && !transactions[index].has_committed)
        {
            return 1;
        }
    }
    return 0;
}

static int wal_has_committed(const BmsWalTransactionState *transactions, size_t transaction_count)
{
    size_t index;
    for (index = 0; index < transaction_count; index++)
    {
        if (transactions[index].has_committed)
        {
            return 1;
        }
    }
    return 0;
}

static BmsStatus compact_uncommitted_pending(const char *wal_path, const BmsWalTransactionState *transactions, size_t transaction_count)
{
    FILE *source;
    FILE *target;
    char temp_path[1024];
    char line[8192];
    char transaction_id[BMS_WAL_ID_SIZE];
    char state[32];
    int transaction_index;
    BmsStatus status;

    if (snprintf(temp_path, sizeof(temp_path), "%s.recovering", wal_path) >= (int)sizeof(temp_path))
    {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    source = fopen(wal_path, "r");
    if (!source)
    {
        return BMS_OK;
    }
    target = fopen(temp_path, "w");
    if (!target)
    {
        fclose(source);
        return BMS_ERR_IO;
    }

    while (fgets(line, sizeof(line), source))
    {
        status = extract_json_string(line, "transaction_id", transaction_id, sizeof(transaction_id));
        if (status != BMS_OK)
        {
            fclose(source);
            fclose(target);
            remove(temp_path);
            return status;
        }
        status = extract_json_string(line, "state", state, sizeof(state));
        if (status != BMS_OK)
        {
            fclose(source);
            fclose(target);
            remove(temp_path);
            return status;
        }

        transaction_index = find_transaction(transactions, transaction_count, transaction_id);
        if (strcmp(state, "pending") == 0 && transaction_index >= 0 && !transactions[transaction_index].has_committed)
        {
            continue;
        }
        if (fputs(line, target) == EOF)
        {
            fclose(source);
            fclose(target);
            remove(temp_path);
            return BMS_ERR_IO;
        }
    }

    fclose(source);
    status = flush_file(target);
    fclose(target);
    if (status != BMS_OK)
    {
        remove(temp_path);
        return status;
    }
    status = replace_file(temp_path, wal_path);
    if (status != BMS_OK)
    {
        remove(temp_path);
        return status;
    }
    return BMS_OK;
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
    unsigned long long valid_records = 0;
    BmsWalTransactionState transactions[BMS_WAL_MAX_TRANSACTIONS];
    size_t transaction_count = 0;
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

    status = scan_wal_transactions(wal_path, transactions, &transaction_count);
    if (status != BMS_OK)
    {
        *recovery_decision = BMS_WAL_RECOVERY_PROTECTED_READ_ONLY;
        wal_log(telemetry, BMS_LOG_ERROR, "n/a", "protected read-only mode entered");
        return BMS_ERR_PROTECTED_MODE;
    }

    if (wal_has_uncommitted_pending(transactions, transaction_count))
    {
        *recovery_decision = BMS_WAL_RECOVERY_PENDING_ROLLBACK;
        wal_log(telemetry, BMS_LOG_WARN, "n/a", "pending wal requires rollback decision");
        return BMS_ERR_RECOVERY_REQUIRED;
    }

    if (wal_has_committed(transactions, transaction_count) && required_snapshot_path && !file_exists(required_snapshot_path))
    {
        *recovery_decision = BMS_WAL_RECOVERY_COMMITTED_MISSING_SNAPSHOT;
        wal_log(telemetry, BMS_LOG_WARN, "n/a", "committed wal missing snapshot");
        return BMS_ERR_RECOVERY_REQUIRED;
    }

    wal_log(telemetry, BMS_LOG_INFO, "n/a", "wal recovery clean");
    return BMS_OK;
}

BmsStatus bms_wal_recover_startup(
    const char *wal_path,
    const char *required_snapshot_path,
    int *recovery_decision)
{
    return bms_wal_recover_startup_with_telemetry(
        wal_path,
        required_snapshot_path,
        recovery_decision,
        NULL);
}

BmsStatus bms_wal_recover_startup_with_telemetry(
    const char *wal_path,
    const char *required_snapshot_path,
    int *recovery_decision,
    const BmsStorageTelemetry *telemetry)
{
    BmsWalTransactionState transactions[BMS_WAL_MAX_TRANSACTIONS];
    size_t transaction_count = 0;
    BmsStatus status;
    int decision = BMS_WAL_RECOVERY_CLEAN;

    if (!wal_path || !recovery_decision)
    {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    status = bms_wal_inspect_startup_with_telemetry(wal_path, required_snapshot_path, &decision, telemetry);
    *recovery_decision = decision;
    if (status == BMS_OK)
    {
        return BMS_OK;
    }
    if (decision == BMS_WAL_RECOVERY_PROTECTED_READ_ONLY)
    {
        return status;
    }
    if (decision == BMS_WAL_RECOVERY_COMMITTED_MISSING_SNAPSHOT)
    {
        wal_log(telemetry, BMS_LOG_WARN, "n/a", "committed wal requires snapshot rebuild");
        return BMS_ERR_RECOVERY_REQUIRED;
    }
    if (decision != BMS_WAL_RECOVERY_PENDING_ROLLBACK)
    {
        return status;
    }

    status = scan_wal_transactions(wal_path, transactions, &transaction_count);
    if (status != BMS_OK)
    {
        *recovery_decision = BMS_WAL_RECOVERY_PROTECTED_READ_ONLY;
        wal_log(telemetry, BMS_LOG_ERROR, "n/a", "protected read-only mode entered");
        return BMS_ERR_PROTECTED_MODE;
    }

    status = compact_uncommitted_pending(wal_path, transactions, transaction_count);
    if (status != BMS_OK)
    {
        return status;
    }

    *recovery_decision = BMS_WAL_RECOVERY_PENDING_ROLLBACK;
    wal_log(telemetry, BMS_LOG_WARN, "n/a", "pending wal rolled back");
    return BMS_OK;
}
