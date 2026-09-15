cmake_minimum_required(VERSION 3.24)
project(ChessBot VERSION 0.10.0 LANGUAGES CXX)

include(CTest)
option(CHESSBOT_SANITIZERS "Enable supported address/undefined behavior sanitizers" OFF)
option(CHESSBOT_SLOW_TESTS "Register full depth-6 PERFT tests" OFF)

find_package(Threads REQUIRED)
add_library(chessbot_core
    src/board/board.cpp src/board/move.cpp src/board/attack_tables.cpp
    src/board/zobrist.cpp src/board/movegen.cpp
    src/eval/evaluation.cpp src/eval/nnue.cpp src/engine/engine.cpp
    src/openings/opening_book.cpp
    src/search/search.cpp src/search/ordering.cpp src/search/transposition_table.cpp
    src/search/time_manager.cpp src/protocol/uci.cpp)
target_include_directories(chessbot_core PUBLIC src)
target_compile_features(chessbot_core PUBLIC cxx_std_20)
set_target_properties(chessbot_core PROPERTIES CXX_EXTENSIONS OFF)

add_library(chessbot_options INTERFACE)
if(MSVC)
    target_compile_options(chessbot_options INTERFACE /W4 /permissive- /utf-8)
    if(CHESSBOT_SANITIZERS)
        # MSVC address sanitizer is incompatible with Debug's /RTC1 checks.
        string(REGEX REPLACE "/RTC[1su]+" "" CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG}")
        target_compile_options(chessbot_options INTERFACE /fsanitize=address /Zi)
        target_link_options(chessbot_options INTERFACE /INCREMENTAL:NO)
    endif()
else()
    target_compile_options(chessbot_options INTERFACE -Wall -Wextra -Wpedantic)
    if(CHESSBOT_SANITIZERS)
        target_compile_options(chessbot_options INTERFACE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(chessbot_options INTERFACE -fsanitize=address,undefined)
    endif()
endif()
target_link_libraries(chessbot_core PUBLIC chessbot_options Threads::Threads)
add_executable(chessbot src/main.cpp)
target_link_libraries(chessbot PRIVATE chessbot_core)

if(BUILD_TESTING)
    add_executable(chessbot_tests tests/test_board.cpp tests/test_perft.cpp tests/test_eval.cpp
        tests/test_nnue.cpp tests/test_search.cpp)
    target_include_directories(chessbot_tests SYSTEM PRIVATE third_party/doctest)
    target_link_libraries(chessbot_tests PRIVATE chessbot_core)
    add_test(NAME rules COMMAND chessbot_tests --test-case-exclude=*slow*)
    add_test(NAME cli_help COMMAND chessbot --help)
    set_tests_properties(rules cli_help PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
    if(CHESSBOT_SLOW_TESTS)
        add_test(NAME perft_full COMMAND chessbot_tests --test-case=*slow*)
        set_tests_properties(perft_full PROPERTIES LABELS slow TIMEOUT 600
            WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
    endif()
endif()
