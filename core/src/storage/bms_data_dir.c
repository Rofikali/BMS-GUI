#include "bms/storage/data_dir.h"

#include "bms/storage/snapshot.h"

#include <stdio.h>
#include <string.h>

#if defined(_WIN32)
#include <direct.h>
#define bms_mkdir(path) _mkdir(path)
#else
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>
#define bms_mkdir(path) mkdir(path, 0775)
#endif

static BmsStatus make_dir_if_needed(const char *path)
{
    if (!path || path[0] == '\0') {
        return BMS_ERR_INVALID_ARGUMENT;
    }
    if (bms_mkdir(path) == 0) {
        return BMS_OK;
    }
#if defined(_WIN32)
    return BMS_OK;
#else
    return errno == EEXIST ? BMS_OK : BMS_ERR_IO;
#endif
}

static BmsStatus join_path(char *buffer, size_t buffer_size, const char *root, const char *suffix)
{
    int written;
    if (!buffer || !root || !suffix) {
        return BMS_ERR_INVALID_ARGUMENT;
    }
    written = snprintf(buffer, buffer_size, "%s/%s", root, suffix);
    return (written > 0 && (size_t)written < buffer_size) ? BMS_OK : BMS_ERR_BUFFER_TOO_SMALL;
}

BmsStatus bms_data_dir_init(const char *root_path, const char *created_at)
{
    static const char *dirs[] = {
        "wal",
        "wal/archive",
        "events",
        "accounting",
        "accounting/snapshots",
        "inventory",
        "inventory/snapshots",
        "billing",
        "billing/snapshots",
        "audit",
        "users",
        "tax",
        "reports",
        "reports/generated",
        "backups",
        "temp"
    };
    char path[512];
    char manifest_path[512];
    char payload[512];
    size_t i;
    BmsStatus status;

    if (!root_path || !created_at) {
        return BMS_ERR_INVALID_ARGUMENT;
    }

    status = make_dir_if_needed(root_path);
    if (status != BMS_OK) {
        return status;
    }
    for (i = 0; i < sizeof(dirs) / sizeof(dirs[0]); ++i) {
        status = join_path(path, sizeof(path), root_path, dirs[i]);
        if (status != BMS_OK) return status;
        status = make_dir_if_needed(path);
        if (status != BMS_OK) return status;
    }

    status = join_path(manifest_path, sizeof(manifest_path), root_path, "manifest.json");
    if (status != BMS_OK) return status;
    if (snprintf(
            payload,
            sizeof(payload),
            "{\"storage_engine\":\"file-jsonl\",\"created_at\":\"%s\"}",
            created_at) >= (int)sizeof(payload)) {
        return BMS_ERR_BUFFER_TOO_SMALL;
    }

    return bms_snapshot_write_atomic(
        manifest_path,
        1,
        created_at,
        "[]",
        0,
        payload);
}
