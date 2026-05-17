#ifndef BMS_STATUS_H
#define BMS_STATUS_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum BmsStatus {
    BMS_OK = 0,
    BMS_ERR_INVALID_ARGUMENT = 1,
    BMS_ERR_IO = 2,
    BMS_ERR_BUFFER_TOO_SMALL = 3,
    BMS_ERR_CHECKSUM = 4,
    BMS_ERR_DUPLICATE_IDEMPOTENCY_KEY = 5,
    BMS_ERR_PARSE = 6,
    BMS_ERR_RECOVERY_REQUIRED = 7,
    BMS_ERR_PROTECTED_MODE = 8
} BmsStatus;

#ifdef __cplusplus
}
#endif

#endif
