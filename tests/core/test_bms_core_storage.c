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

int main(void)
{
    test_record_checksum_round_trip();
    test_jsonl_append_and_verify();
    test_duplicate_idempotency_key_rejected();
    test_corrupt_checksum_rejected();
    test_wal_pending_and_committed_records();

    return 0;
}
