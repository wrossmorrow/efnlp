cmake_minimum_required(VERSION 3.10)

project(efnlp CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)
set(CMAKE_POSITION_INDEPENDENT_CODE TRUE)
set(CMAKE_CXX_FLAGS "-Wall -Wextra -O3")

set(CMAKE_INCLUDE_CURRENT_DIR ON)

find_package(spdlog REQUIRED)
find_package(nlohmann_json 3.2.0 REQUIRED)

find_package(Protobuf REQUIRED)
include_directories(${Protobuf_INCLUDE_DIRS})
protobuf_generate_cpp(PROTO_SRCS PROTO_HDRS ../proto/efnlp.proto)

include_directories(${CMAKE_CURRENT_BINARY_DIR})

add_executable(efnlp++ main.cpp ${PROTO_SRCS} ${PROTO_HDRS})
target_link_libraries(efnlp++ PRIVATE spdlog::spdlog nlohmann_json::nlohmann_json ${Protobuf_LIBRARIES})
