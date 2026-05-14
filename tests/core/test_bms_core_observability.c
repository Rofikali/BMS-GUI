#include "bms/observability/logger.h"
#include "bms/observability/metrics.h"
#include "bms/status.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void remove_if_exists(const char *path)
{
    remove(path);
}

static void test_logger_writes_jsonl(void)
{
    const char *path = "test_core.log.jsonl";
    BmsLogger logger;
    FILE *file;
    char line[1024];

    remove_if_exists(path);

    assert(bms_logger_init(&logger, path, BMS_LOG_INFO) == BMS_OK);
    assert(bms_logger_write(
               &logger,
               BMS_LOG_INFO,
               "2026-05-13T00:00:00Z",
               "storage",
               "corr_1",
               "append complete") == BMS_OK);

    file = fopen(path, "r");
    assert(file != NULL);
    assert(fgets(line, sizeof(line), file) != NULL);
    fclose(file);

    assert(strstr(line, "\"level\":\"info\"") != NULL);
    assert(strstr(line, "\"module\":\"storage\"") != NULL);
    assert(strstr(line, "\"correlation_id\":\"corr_1\"") != NULL);

    remove_if_exists(path);
}

static void test_counter_json(void)
{
    BmsCounter counter;
    char json[256];

    assert(bms_counter_init(&counter, "storage.records_appended") == BMS_OK);
    assert(bms_counter_inc(&counter, 2) == BMS_OK);
    assert(bms_counter_inc(&counter, 3) == BMS_OK);
    assert(bms_counter_to_json(&counter, json, sizeof(json)) == BMS_OK);
    assert(strcmp(json, "{\"metric_type\":\"counter\",\"name\":\"storage.records_appended\",\"value\":5}") == 0);
}

int main(void)
{
    test_logger_writes_jsonl();
    test_counter_json();
    return 0;
}
