#ifndef BMS_OBSERVABILITY_METRICS_H
#define BMS_OBSERVABILITY_METRICS_H

#include <stddef.h>

#include "bms/status.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BMS_METRIC_NAME_LEN 96

typedef struct BmsCounter {
    char name[BMS_METRIC_NAME_LEN];
    unsigned long long value;
} BmsCounter;

BmsStatus bms_counter_init(BmsCounter *counter, const char *name);
BmsStatus bms_counter_inc(BmsCounter *counter, unsigned long long amount);
BmsStatus bms_counter_to_json(
    const BmsCounter *counter,
    char *buffer,
    size_t buffer_size
);

#ifdef __cplusplus
}
#endif

#endif
