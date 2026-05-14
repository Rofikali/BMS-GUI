#include "bms/observability/logger.h"
#include "bms/observability/metrics.h"
#include "bms/observability/storage_telemetry.h"
#include "bms/status.h"
#include "bms/storage/jsonl_store.h"
#include "bms/storage/record.h"
#include "bms/wal/wal.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void remove_if_exists(const char *path)
{
    remove(path);
}

static BmsRecord sample_record(const char *record_id, const char *idempotency_key)
{
    BmsRecord record;
    memset(&record, 0, sizeof(record));
    record.schema_version = 1;
    record.sequence = 0;
    record.record_id = record_id;
    record.record_type = "test.record";
    record.created_at = "2026-05-13T00:00:00Z";
    record.actor_id = "usr_test";
    record.correlation_id = "corr_test";
    record.idempotency_key = idempotency_key;
    record.payload_json = "{\"amount_minor\":1000}";
    return record;
}

static void test_record_checksum_round_trip(void)
{
    BmsRecord record = sample_record("rec_1", "idem_1");
    char line[8192];

    record.sequence = 1;
    assert(bms_record_compute_checksum(&record) == BMS_OK);
    assert(strncmp(record.checksum, "sha256:", 7) == 0);
    assert(bms_record_to_json_line(&record, line, sizeof(line)) == BMS_OK);
    assert(bms_record_verify_json_line(line) == BMS_OK);
}

static void test_key_order_variation(void)
{
    BmsRecord record = sample_record("rec_key", "idem_key");
    char line1[8192];
    char line2[8192];

    record.sequence = 1;
    assert(bms_record_compute_checksum(&record) == BMS_OK);
    /* line produced by serializer */
    assert(bms_record_to_json_line(&record, line1, sizeof(line1)) == BMS_OK);
    assert(bms_record_verify_json_line(line1) == BMS_OK);

    /* manually reorder fields but keep payload followed immediately by checksum */
    int written = snprintf(
        line2,
        sizeof(line2),
        "{\"record_type\":\"%s\",\"schema_version\":%d,\"sequence\":%llu,\"record_id\":\"%s\",\"payload\":%s,\"checksum\":\"%s\",\"created_at\":\"%s\",\"actor_id\":\"%s\",\"correlation_id\":\"%s\",\"idempotency_key\":\"%s\"}\n",
        record.record_type,
        record.schema_version,
        record.sequence,
        record.record_id,
        record.payload_json,
        record.checksum,
        record.created_at,
        record.actor_id,
        record.correlation_id,
        record.idempotency_key);

    assert(written > 0 && (size_t)written < sizeof(line2));
    assert(bms_record_verify_json_line(line2) == BMS_OK);
}

static void test_jsonl_append_and_verify(void)
{
    const char *path = "test_storage_records.jsonl";
    BmsRecord record = sample_record("rec_2", "idem_2");
    unsigned long long valid_records = 0;
    unsigned long long next_sequence = 0;

    remove_if_exists(path);

    assert(bms_jsonl_append_record(path, &record) == BMS_OK);
    assert(record.sequence == 1);
    assert(bms_jsonl_verify_file(path, &valid_records) == BMS_OK);
    assert(valid_records == 1);
    assert(bms_jsonl_next_sequence(path, &next_sequence) == BMS_OK);
    assert(next_sequence == 2);

    remove_if_exists(path);
}

static void test_duplicate_idempotency_key_rejected(void)
{
    const char *path = "test_duplicate_records.jsonl";
    BmsRecord first = sample_record("rec_3", "idem_duplicate");
    BmsRecord second = sample_record("rec_4", "idem_duplicate");

    remove_if_exists(path);

    assert(bms_jsonl_append_record(path, &first) == BMS_OK);
    assert(bms_jsonl_append_record(path, &second) == BMS_ERR_DUPLICATE_IDEMPOTENCY_KEY);

    remove_if_exists(path);
}

static void test_corrupt_checksum_rejected(void)
{
    const char *path = "test_corrupt_records.jsonl";
    FILE *file;
    unsigned long long valid_records = 0;

    remove_if_exists(path);

    file = fopen(path, "w");
    assert(file != NULL);
    fputs("{\"schema_version\":1,\"sequence\":1,\"record_id\":\"rec_bad\",\"record_type\":\"test.record\",\"created_at\":\"2026-05-13T00:00:00Z\",\"actor_id\":\"usr_test\",\"correlation_id\":\"corr_test\",\"idempotency_key\":\"idem_bad\",\"payload\":{\"amount_minor\":9999},\"checksum\":\"sha256:bad\"}\n", file);
    fclose(file);

    assert(bms_jsonl_verify_file(path, &valid_records) == BMS_ERR_CHECKSUM);

    remove_if_exists(path);
}

static void test_wal_pending_and_committed_records(void)
{
    const char *path = "test_wal.jsonl";
    unsigned long long valid_records = 0;

    remove_if_exists(path);

    assert(bms_wal_append_pending(
               path,
               "txn_1",
               "2026-05-13T00:00:00Z",
               "usr_test",
               "corr_txn_1",
               "{\"operation\":\"invoice.create\"}") == BMS_OK);

    assert(bms_wal_append_committed(
               path,
               "txn_1",
               "2026-05-13T00:00:01Z",
               "usr_test",
               "corr_txn_1") == BMS_OK);

    assert(bms_jsonl_verify_file(path, &valid_records) == BMS_OK);
    assert(valid_records == 2);

    remove_if_exists(path);
}

static void test_storage_and_wal_emit_observability(void)
{
    const char *records_path = "test_observe_records.jsonl";
    const char *wal_path = "test_observe_wal.jsonl";
    const char *log_path = "test_observe.log.jsonl";
    BmsRecord record = sample_record("rec_observe", "idem_observe");
    BmsLogger logger;
    BmsCounter storage_records_appended;
    BmsCounter storage_checksum_failures;
    BmsCounter storage_duplicate_idempotency_keys;
    BmsCounter storage_verify_success;
    BmsCounter wal_pending_appended;
    BmsCounter wal_committed_appended;
    BmsStorageTelemetry telemetry;
    FILE *file;
    char line[1024];
    int saw_storage_append = 0;
    int saw_wal_pending = 0;
    int saw_wal_committed = 0;

    remove_if_exists(records_path);
    remove_if_exists(wal_path);
    remove_if_exists(log_path);

    assert(bms_logger_init(&logger, log_path, BMS_LOG_INFO) == BMS_OK);
    assert(bms_counter_init(&storage_records_appended, "storage.records_appended") == BMS_OK);
    assert(bms_counter_init(&storage_checksum_failures, "storage.checksum_failures") == BMS_OK);
    assert(bms_counter_init(&storage_duplicate_idempotency_keys, "storage.duplicate_idempotency_keys") == BMS_OK);
    assert(bms_counter_init(&storage_verify_success, "storage.verify_success") == BMS_OK);
    assert(bms_counter_init(&wal_pending_appended, "wal.pending_appended") == BMS_OK);
    assert(bms_counter_init(&wal_committed_appended, "wal.committed_appended") == BMS_OK);

    telemetry.logger = &logger;
    telemetry.storage_records_appended = &storage_records_appended;
    telemetry.storage_checksum_failures = &storage_checksum_failures;
    telemetry.storage_duplicate_idempotency_keys = &storage_duplicate_idempotency_keys;
    telemetry.storage_verify_success = &storage_verify_success;
    telemetry.wal_pending_appended = &wal_pending_appended;
    telemetry.wal_committed_appended = &wal_committed_appended;

    assert(bms_jsonl_append_record_with_telemetry(records_path, &record, &telemetry) == BMS_OK);
    assert(bms_wal_append_pending_with_telemetry(
               wal_path,
               "txn_observe",
               "2026-05-14T00:00:00Z",
               "usr_test",
               "corr_observe",
               "{\"operation\":\"observe\"}",
               &telemetry) == BMS_OK);
    assert(bms_wal_append_committed_with_telemetry(
               wal_path,
               "txn_observe",
               "2026-05-14T00:00:01Z",
               "usr_test",
               "corr_observe",
               &telemetry) == BMS_OK);

    assert(storage_records_appended.value == 3);
    assert(storage_checksum_failures.value == 0);
    assert(storage_duplicate_idempotency_keys.value == 0);
    assert(wal_pending_appended.value == 1);
    assert(wal_committed_appended.value == 1);

    file = fopen(log_path, "r");
    assert(file != NULL);
    while (fgets(line, sizeof(line), file))
    {
        if (strstr(line, "record appended"))
        {
            saw_storage_append = 1;
        }
        if (strstr(line, "wal pending appended"))
        {
            saw_wal_pending = 1;
        }
        if (strstr(line, "wal committed appended"))
        {
            saw_wal_committed = 1;
        }
    }
    fclose(file);

    assert(saw_storage_append == 1);
    assert(saw_wal_pending == 1);
    assert(saw_wal_committed == 1);

    remove_if_exists(records_path);
    remove_if_exists(wal_path);
    remove_if_exists(log_path);
}

int main(void)
{
    test_record_checksum_round_trip();
    test_jsonl_append_and_verify();
    test_duplicate_idempotency_key_rejected();
    test_corrupt_checksum_rejected();
    test_wal_pending_and_committed_records();
    test_storage_and_wal_emit_observability();

    return 0;
}
