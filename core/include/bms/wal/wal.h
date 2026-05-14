#ifndef BMS_WAL_WAL_H
#define BMS_WAL_WAL_H

#include "bms/status.h"

#ifdef __cplusplus
extern "C" {
#endif

BmsStatus bms_wal_append_pending(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id,
    const char *payload_json
);

BmsStatus bms_wal_append_committed(
    const char *wal_path,
    const char *transaction_id,
    const char *created_at,
    const char *actor_id,
    const char *correlation_id
);

#ifdef __cplusplus
}
#endif

#endif
