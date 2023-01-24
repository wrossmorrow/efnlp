cmake_minimum_required(VERSION 3.10)

project(efnlp CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)
set(CMAKE_POSITION_INDEPENDENT_CODE TRUE)

find_package(spdlog REQUIRED)

add_executable(efnlp main.cpp)
target_link_libraries(efnlp PRIVATE spdlog::spdlog)
