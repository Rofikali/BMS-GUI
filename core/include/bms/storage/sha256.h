#ifndef BMS_STORAGE_SHA256_H
#define BMS_STORAGE_SHA256_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

void bms_sha256_hex(const unsigned char *data, size_t len, char out_hex[65]);

#ifdef __cplusplus
}
#endif

#endif
