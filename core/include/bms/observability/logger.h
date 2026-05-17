#ifndef BMS_OBSERVABILITY_LOGGER_H
#define BMS_OBSERVABILITY_LOGGER_H

#include "bms/status.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum BmsLogLevel {
    BMS_LOG_DEBUG = 0,
    BMS_LOG_INFO = 1,
    BMS_LOG_WARN = 2,
    BMS_LOG_ERROR = 3
} BmsLogLevel;

typedef struct BmsLogger {
    char path[512];
    BmsLogLevel min_level;
} BmsLogger;

BmsStatus bms_logger_init(BmsLogger *logger, const char *path, BmsLogLevel min_level);
BmsStatus bms_logger_write(
    BmsLogger *logger,
    BmsLogLevel level,
    const char *timestamp,
    const char *module,
    const char *correlation_id,
    const char *message
);

const char *bms_log_level_name(BmsLogLevel level);

#ifdef __cplusplus
}
#endif

#endif
