cmake_minimum_required(VERSION 3.16)

project(BMSGUI LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

set(BMS_CORE_SOURCES
    core/src/observability/bms_logger.c
    core/src/observability/bms_metrics.c
    core/src/storage/bms_jsonl_store.c
    core/src/storage/bms_record.c
    core/src/storage/bms_sha256.c
    core/src/storage/bms_snapshot.c
    core/src/storage/bms_data_dir.c
    core/src/wal/bms_wal.c
)

add_library(bms_core ${BMS_CORE_SOURCES})
add_library(bms_core_python SHARED ${BMS_CORE_SOURCES})

target_include_directories(bms_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/core/include
)

target_include_directories(bms_core_python
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/core/include
)

if(MSVC)
    target_compile_options(bms_core PRIVATE /W4)
    target_compile_options(bms_core_python PRIVATE /W4)
else()
    target_compile_options(bms_core PRIVATE -Wall -Wextra -Wpedantic)
    target_compile_options(bms_core_python PRIVATE -Wall -Wextra -Wpedantic)
endif()

enable_testing()

add_executable(test_bms_core_storage
    tests/core/test_bms_core_storage.c
)

target_link_libraries(test_bms_core_storage PRIVATE bms_core)

add_test(NAME bms_core_storage COMMAND test_bms_core_storage)

add_executable(test_bms_core_observability
    tests/core/test_bms_core_observability.c
)

target_link_libraries(test_bms_core_observability PRIVATE bms_core)

add_test(NAME bms_core_observability COMMAND test_bms_core_observability)
