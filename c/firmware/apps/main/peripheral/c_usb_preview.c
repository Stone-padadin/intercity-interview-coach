#include "c_usb_preview.h"
#include "driver/uart.h"
#include "esp_heap_caps.h"
#include "esp_jpeg_enc.h"
#include "esp_log.h"
#include "esp_rom_crc.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "qm_log.h"
#include <stdio.h>

#define WIDTH 240u
#define HEIGHT 320u
#define RAW_SIZE (WIDTH*HEIGHT*2u)
#define JPEG_CAPACITY 65536u
static uint8_t *s_yuyv,*s_jpeg;
static jpeg_enc_handle_t s_encoder;
static uint64_t s_last_ms;
typedef struct __attribute__((packed)) {
    uint8_t magic[8];
    uint32_t sequence;
    uint16_t width,height;
    uint32_t size,crc;
} preview_header_t;
_Static_assert(sizeof(preview_header_t)==24,"USB preview header must be 24 bytes");

esp_err_t c_usb_preview_init(void)
{
    s_yuyv=heap_caps_aligned_alloc(16,RAW_SIZE,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    s_jpeg=heap_caps_malloc(JPEG_CAPACITY,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if (!s_yuyv || !s_jpeg) { return ESP_ERR_NO_MEM; }
    jpeg_enc_config_t config=DEFAULT_JPEG_ENC_CONFIG();
    config.width=WIDTH; config.height=HEIGHT;
    config.src_type=JPEG_PIXEL_FORMAT_YCbYCr;
    config.subsampling=JPEG_SUBSAMPLE_420;
    config.quality=60; config.task_enable=false;
    if (jpeg_enc_open(&config,&s_encoder)!=JPEG_ERR_OK) { return ESP_FAIL; }
    if (!uart_is_driver_installed(UART_NUM_0)) {
        esp_err_t err=uart_driver_install(UART_NUM_0,256,8192,0,NULL,0);
        if (err!=ESP_OK) { return err; }
    }
    uart_wait_tx_done(UART_NUM_0,pdMS_TO_TICKS(1000));
    esp_log_level_set("*",ESP_LOG_NONE);
    qm_set_log_level(QM_LL_NONE);
    return uart_set_baudrate(UART_NUM_0,921600);
}

void c_usb_preview_frame(const uint8_t *uyvy,size_t size,uint16_t width,uint16_t height,uint32_t sequence)
{
    if (!s_encoder || size!=RAW_SIZE || width!=WIDTH || height!=HEIGHT) { return; }
    uint64_t now=(uint64_t)(esp_timer_get_time()/1000);
    if (now-s_last_ms<333) { return; }
    s_last_ms=now;
    /* Encoder's YUYV input is supported by all versions used in this SDK. */
    for (size_t i=0;i<size;i+=4) {
        s_yuyv[i]=uyvy[i+1]; s_yuyv[i+1]=uyvy[i];
        s_yuyv[i+2]=uyvy[i+3]; s_yuyv[i+3]=uyvy[i+2];
    }
    int jpeg_size=0;
    jpeg_error_t err=jpeg_enc_process(s_encoder,s_yuyv,RAW_SIZE,s_jpeg,JPEG_CAPACITY,&jpeg_size);
    if (err!=JPEG_ERR_OK || jpeg_size<4) {
        printf("\nCPREVIEW_ERROR encode=%d\n",(int)err);
        vTaskDelay(pdMS_TO_TICKS(10)); return;
    }
    preview_header_t header={.magic={'C','V','J','P','G','0','0','1'},
        .sequence=sequence,.width=width,.height=height,.size=(uint32_t)jpeg_size,
        .crc=esp_rom_crc32_le(0,s_jpeg,jpeg_size)};
    uart_write_bytes(UART_NUM_0,&header,sizeof(header));
    for (int offset=0;offset<jpeg_size;offset+=2048) {
        int count=jpeg_size-offset; if (count>2048) { count=2048; }
        uart_write_bytes(UART_NUM_0,s_jpeg+offset,count);
        if ((offset&8191)==6144) { vTaskDelay(pdMS_TO_TICKS(10)); }
    }
    uart_wait_tx_done(UART_NUM_0,pdMS_TO_TICKS(1500));
    vTaskDelay(pdMS_TO_TICKS(10));
}
