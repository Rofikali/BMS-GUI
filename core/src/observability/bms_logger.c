#define _POSIX_C_SOURCE 200809L

#include "bms/observability/logger.h"

#include <stdio.h>
#include <string.h>

#if defined(_WIN32)
#include <io.h>
#define bms_fsync _commit
#else
#include <unistd.h>
#define bms_fsync fsync
#endif

const char *bms_log_level_name(BmsLogLevel level)
{
    switch (level) {
        case BMS_LOG_DEBUG:
            return "debug";
        case BMS_LOG_INFO:
            return "info";
        case BMS_LOG_WARN:
            return "warn";
        case BMS_LOG_ERROR:
            return "error";
        default:
            return "unknown";
    }
}

BmsStatus bms_logger_init(BmsLogger *logger, const char *path, BmsLogLevel min_level)
{
    size_t len;

    if (!logger || !path) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    len = strlen(path);
    if (len == 0 || len >= sizeof(logger->path)) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    memcpy(logger->path, path, len + 1);
    logger->min_level = min_level;
    return BMS_OK;
}

BmsStatus bms_logger_write(
    BmsLogger *logger,
    BmsLogLevel level,
    const char *timestamp,
    const char *module,
    const char *correlation_id,
    const char *message
)
{
    FILE *file;

    if (!logger || !timestamp || !module || !correlation_id || !message) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    if (level < logger->min_level) {
        return BMS_OK;
    }

    file = fopen(logger->path, "a");
    if (!file) {
        return BMS_ERR_IO;
    }

    if (fprintf(
            file,
            "{\"timestamp\":\"%s\",\"level\":\"%s\",\"module\":\"%s\",\"correlation_id\":\"%s\",\"message\":\"%s\"}\n",
            timestamp,
            bms_log_level_name(level),
            module,
            correlation_id,
            message) < 0) {
        fclose(file);
        return BMS_ERR_IO;
    }

    if (fflush(file) != 0 || bms_fsync(fileno(file)) != 0) {
        fclose(file);
        return BMS_ERR_IO;
    }

    fclose(file);
    return BMS_OK;
}
