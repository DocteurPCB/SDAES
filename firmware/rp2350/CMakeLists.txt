# Firmware SDAES - Raspberry Pi Pico 2 (RP2350)
#
#   git clone https://github.com/raspberrypi/pico-sdk   (SDK >= 2.0)
#   git clone https://github.com/carlk3/no-OS-FatFS-SD-SDIO-SPI-RPi-Pico lib/fatfs-sd
#   export PICO_SDK_PATH=/chemin/vers/pico-sdk
#   cmake -B build -DPICO_BOARD=pico2 && cmake --build build
#   -> build/sdaes_fw.uf2 à copier sur le Pico 2 (bouton BOOTSEL)
cmake_minimum_required(VERSION 3.13)

set(PICO_BOARD pico2 CACHE STRING "Carte")
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(sdaes_fw C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

add_subdirectory(lib/fatfs-sd/src build_fatfs)

add_executable(sdaes_fw
    src/main.c
    src/qlink.c
    src/neo_loader.c
    src/mapper.c
    src/browser.c
    src/hw_config.c
)
pico_generate_pio_header(sdaes_fw ${CMAKE_CURRENT_LIST_DIR}/src/qlink.pio)

target_link_libraries(sdaes_fw
    pico_stdlib
    hardware_pio
    hardware_dma
    no-OS-FatFS-SD-SDIO-SPI-RPi-Pico
)
target_compile_options(sdaes_fw PRIVATE -Wall -Wextra -O2)

pico_enable_stdio_usb(sdaes_fw 1)
pico_enable_stdio_uart(sdaes_fw 0)
pico_add_extra_outputs(sdaes_fw)
