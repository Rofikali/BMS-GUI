#include "bms/observability/metrics.h"

#include <stdio.h>
#include <string.h>

BmsStatus bms_counter_init(BmsCounter *counter, const char *name)
{
    size_t len;

    if (!counter || !name) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    len = strlen(name);
    if (len == 0 || len >= sizeof(counter->name)) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    memcpy(counter->name, name, len + 1);
    counter->value = 0;
    return BMS_OK;
}

BmsStatus bms_counter_inc(BmsCounter *counter, unsigned long long amount)
{
    if (!counter) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    counter->value += amount;
    return BMS_OK;
}

BmsStatus bms_counter_to_json(
    const BmsCounter *counter,
    char *buffer,
    size_t buffer_size
)
{
    int written;

    if (!counter || !buffer || buffer_size == 0) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    written = snprintf(
        buffer,
        buffer_size,
        "{\"metric_type\":\"counter\",\"name\":\"%s\",\"value\":%llu}",
        counter->name,
        counter->value);

    if (written < 0 || (size_t)written >= buffer_size) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    return BMS_OK;
}
