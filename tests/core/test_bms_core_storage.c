#include "bms/observability/logger.h"
#include "bms/observability/metrics.h"
#include "bms/observability/storage_telemetry.h"
#include "bms/status.h"
#include "bms/storage/data_dir.h"
#include "bms/storage/jsonl_store.h"
#include "bms/storage/record.h"
#include "bms/storage/snapshot.h"
#include "bms/wal/wal.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void remove_if_exists(const char *path)
{
    remove(path);
}

static int file_exists(const char *path)
{
    FILE *file = fopen(path, "r");
    if (!file)
    {
        return 0;
    }
    fclose(file);
    return 1;
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

static void test_data_dir_init_writes_required_layout_and_manifest(void)
{
    const char *root = "test_bms_data_core";
    const char *manifest = "test_bms_data_core/manifest.json";
    const char *wal_archive = "test_bms_data_core/wal/archive/.probe";
    FILE *file;

    assert(bms_data_dir_init(root, "2026-05-14T00:00:00Z") == BMS_OK);
    assert(bms_snapshot_verify_file(manifest) == BMS_OK);

    file = fopen(wal_archive, "w");
    assert(file != NULL);
    fputs("ok", file);
    fclose(file);
    assert(file_exists(wal_archive) == 1);

    remove_if_exists(wal_archive);
    remove_if_exists(manifest);
}

static void test_snapshot_write_atomic_and_verify(void)
{
    const char *path = "test_trial_balance.snapshot.json";
    FILE *file;
    char line[9000];

    remove_if_exists(path);
    remove_if_exists("test_trial_balance.snapshot.json.tmp");

    assert(bms_snapshot_write_atomic(
               path,
               1,
               "2026-05-14T00:00:00Z",
               "[\"accounting/journal_entries.jsonl\"]",
               42,
               "{\"debit_total_minor\":118000,\"credit_total_minor\":118000}") == BMS_OK);
    assert(file_exists(path) == 1);
    assert(file_exists("test_trial_balance.snapshot.json.tmp") == 0);
    assert(bms_snapshot_verify_file(path) == BMS_OK);

    file = fopen(path, "w");
    assert(file != NULL);
    fputs("{\"generated_at\":\"2026-05-14T00:00:00Z\",\"last_applied_sequence\":42,\"payload\":{\"debit_total_minor\":999999,\"credit_total_minor\":118000},\"schema_version\":1,\"source_files\":[\"accounting/journal_entries.jsonl\"],\"checksum\":\"sha256:0000000000000000000000000000000000000000000000000000000000000000\"}\n", file);
    fclose(file);
    (void)line;
    assert(bms_snapshot_verify_file(path) == BMS_ERR_CHECKSUM);

    remove_if_exists(path);
}

static void test_wal_detects_pending_on_startup(void)
{
    const char *path = "test_wal_pending_startup.jsonl";
    int decision = -1;

    remove_if_exists(path);
    assert(bms_wal_append_pending(
               path,
               "txn_pending",
               "2026-05-14T00:00:00Z",
               "usr_test",
               "corr_pending",
               "{\"operation\":\"invoice.create\"}") == BMS_OK);

    assert(bms_wal_inspect_startup(path, NULL, &decision) == BMS_ERR_RECOVERY_REQUIRED);
    assert(decision == BMS_WAL_RECOVERY_PENDING_ROLLBACK);

    remove_if_exists(path);
}

static void test_wal_detects_committed_missing_snapshot(void)
{
    const char *path = "test_wal_committed_startup.jsonl";
    const char *snapshot = "test_missing_snapshot.json";
    int decision = -1;

    remove_if_exists(path);
    remove_if_exists(snapshot);
    assert(bms_wal_append_pending(
               path,
               "txn_committed",
               "2026-05-14T00:00:00Z",
               "usr_test",
               "corr_committed",
               "{\"operation\":\"invoice.create\"}") == BMS_OK);
    assert(bms_wal_append_committed(
               path,
               "txn_committed",
               "2026-05-14T00:00:01Z",
               "usr_test",
               "corr_committed") == BMS_OK);

    assert(bms_wal_inspect_startup(path, snapshot, &decision) == BMS_ERR_RECOVERY_REQUIRED);
    assert(decision == BMS_WAL_RECOVERY_COMMITTED_MISSING_SNAPSHOT);

    remove_if_exists(path);
}

static void test_wal_corruption_enters_protected_mode(void)
{
    const char *path = "test_wal_corrupt_startup.jsonl";
    FILE *file;
    int decision = -1;

    remove_if_exists(path);
    file = fopen(path, "w");
    assert(file != NULL);
    fputs("{\"schema_version\":1,\"sequence\":1,\"record_id\":\"wal_bad\",\"record_type\":\"wal.transaction\",\"created_at\":\"2026-05-14T00:00:00Z\",\"actor_id\":\"usr_test\",\"correlation_id\":\"corr_bad\",\"idempotency_key\":\"wal_bad\",\"payload\":{\"transaction_id\":\"txn_bad\",\"state\":\"pending\",\"payload\":{}},\"checksum\":\"sha256:bad\"}\n", file);
    fclose(file);

    assert(bms_wal_inspect_startup(path, NULL, &decision) == BMS_ERR_PROTECTED_MODE);
    assert(decision == BMS_WAL_RECOVERY_PROTECTED_READ_ONLY);

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

static void test_payload_representation_difference(void)
{
    BmsRecord a = sample_record("rec_num1", "idem_num1");
    BmsRecord b = sample_record("rec_num2", "idem_num2");
    char line_a[8192];
    char line_b[8192];
    char modified[8192];

    a.sequence = 1;
    b.sequence = 1;
    a.payload_json = "{\"amount\":1000}";
    b.payload_json = "{\"amount\":1000.0}";

    assert(bms_record_compute_checksum(&a) == BMS_OK);
    assert(bms_record_compute_checksum(&b) == BMS_OK);
    /* Different payload representation should produce different checksums (payload is not canonicalized by core). */
    assert(strcmp(a.checksum, b.checksum) != 0);

    assert(bms_record_to_json_line(&a, line_a, sizeof(line_a)) == BMS_OK);
    assert(bms_record_to_json_line(&b, line_b, sizeof(line_b)) == BMS_OK);
    assert(bms_record_verify_json_line(line_a) == BMS_OK);
    assert(bms_record_verify_json_line(line_b) == BMS_OK);

    /* If payload is swapped but checksum left unchanged, verification must fail. */
    int written = snprintf(
        modified,
        sizeof(modified),
        "{\"schema_version\":%d,\"sequence\":%llu,\"record_id\":\"%s\",\"record_type\":\"%s\",\"created_at\":\"%s\",\"actor_id\":\"%s\",\"correlation_id\":\"%s\",\"idempotency_key\":\"%s\",\"payload\":%s,\"checksum\":\"%s\"}\n",
        a.schema_version,
        a.sequence,
        a.record_id,
        a.record_type,
        a.created_at,
        a.actor_id,
        a.correlation_id,
        a.idempotency_key,
        b.payload_json, /* use b's payload but a's checksum */
        a.checksum);
    assert(written > 0 && (size_t)written < sizeof(modified));
    assert(bms_record_verify_json_line(modified) == BMS_ERR_CHECKSUM);
}

static void test_unicode_composed_vs_decomposed(void)
{
    BmsRecord a = sample_record("rec_u1", "idem_u1");
    BmsRecord b = sample_record("rec_u2", "idem_u2");
    char line_a[8192];
    char line_b[8192];

    a.sequence = 1;
    b.sequence = 1;

    /* U+00E9 (é) as single codepoint in UTF-8 */
    a.payload_json = "{\"note\":\"\xC3\xA9\"}";
    /* 'e' + combining acute U+0301 (e + ́) */
    b.payload_json = "{\"note\":\"e\xCC\x81\"}";

    assert(bms_record_compute_checksum(&a) == BMS_OK);
    assert(bms_record_compute_checksum(&b) == BMS_OK);
    /* Without Unicode normalization, composed and decomposed forms differ. */
    assert(strcmp(a.checksum, b.checksum) != 0);

    assert(bms_record_to_json_line(&a, line_a, sizeof(line_a)) == BMS_OK);
    assert(bms_record_to_json_line(&b, line_b, sizeof(line_b)) == BMS_OK);
    assert(bms_record_verify_json_line(line_a) == BMS_OK);
    assert(bms_record_verify_json_line(line_b) == BMS_OK);
}

int main(void)
{
    test_record_checksum_round_trip();
    test_jsonl_append_and_verify();
    test_duplicate_idempotency_key_rejected();
    test_corrupt_checksum_rejected();
    test_wal_pending_and_committed_records();
    test_data_dir_init_writes_required_layout_and_manifest();
    test_snapshot_write_atomic_and_verify();
    test_wal_detects_pending_on_startup();
    test_wal_detects_committed_missing_snapshot();
    test_wal_corruption_enters_protected_mode();
    test_storage_and_wal_emit_observability();
    test_payload_representation_difference();
    test_unicode_composed_vs_decomposed();

    return 0;
}
