#pragma once
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"
esp_err_t c_usb_preview_init(void);
void c_usb_preview_frame(const uint8_t *uyvy,size_t size,uint16_t width,uint16_t height,uint32_t sequence);
