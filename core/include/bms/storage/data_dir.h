#ifndef BMS_STORAGE_DATA_DIR_H
#define BMS_STORAGE_DATA_DIR_H

#include "bms/status.h"

#ifdef __cplusplus
extern "C" {
#endif

BmsStatus bms_data_dir_init(const char *root_path, const char *created_at);

#ifdef __cplusplus
}
#endif

#endif
