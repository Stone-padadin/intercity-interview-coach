/* Run the actual live worker one job at a time with fake RTOS/model/hardware.
 * This tests pause during inference; it is not real multicore or model evidence. */
#include "c_live_pose.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "qm_cli.h"
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>

static uint64_t now_ms;
static int token,notification,inference_action;
static unsigned inferences;
static void (*worker_fn)(void *);
static jmp_buf yield_worker;
void spi_live_test_log(const char *tag,const char *format,...) { (void)tag; (void)format; }
int64_t esp_timer_get_time(void) { return (int64_t)(now_ms*1000); }
void *heap_caps_malloc(size_t size,int caps) { (void)caps; return malloc(size); }
void heap_caps_free(void *p) { free(p); }
size_t heap_caps_get_free_size(int caps) { (void)caps; return 1000000; }
SemaphoreHandle_t xSemaphoreCreateBinary(void) { token=0; return &token; }
void vSemaphoreDelete(SemaphoreHandle_t sem) { (void)sem; }
int xSemaphoreTake(SemaphoreHandle_t sem,uint32_t ticks)
{ (void)sem; (void)ticks; if (!token) { return 0; } token=0; return 1; }
int xSemaphoreGive(SemaphoreHandle_t sem) { (void)sem; token=1; return 1; }
int xTaskCreatePinnedToCoreWithCaps(void (*worker)(void *),const char *name,unsigned stack,
    void *arg,unsigned priority,TaskHandle_t *handle,int core,int caps)
{
    (void)name; (void)stack; (void)arg; (void)priority; (void)core; (void)caps;
    worker_fn=worker; *handle=(void *)1; return 1;
}
unsigned ulTaskNotifyTake(int clear,uint32_t ticks)
{
    (void)clear; (void)ticks;
    if (!notification) { longjmp(yield_worker,1); }
    notification=0; return 1;
}
void xTaskNotifyGive(TaskHandle_t task) { (void)task; notification=1; }
void vTaskDelay(unsigned ticks) { (void)ticks; }
int qm_cli_register_command(const struct qm_cli_command *command) { (void)command; return 0; }
esp_err_t yolo11_pose_init(void) { return ESP_OK; }
void yolo11_pose_prealloc_buffers(void) {}
esp_err_t yolo11_pose_uyvy_to_rgb888(const uint8_t *raw,size_t len,uint16_t width,
    uint16_t height,uint8_t **rgb,uint16_t *w,uint16_t *h)
{
    static uint8_t pixel[3]; (void)raw; (void)len;
    *rgb=pixel; *w=width; *h=height; return ESP_OK;
}
esp_err_t yolo11_pose_analyze_rgb888(uint8_t *rgb,uint16_t width,uint16_t height,
    const char *name,yolo11_pose_frame_result_t *result)
{
    (void)rgb; (void)width; (void)height; (void)name;
    inferences++;
    *result=(yolo11_pose_frame_result_t){.status=YOLO11_POSE_FRAME_OK,.person_count=1,
        .geometry={.valid=true,.angle_deg=0,.scale=100}};
    if (inference_action) {
        c_live_pose_set_enabled(false);
        if (inference_action==2) { c_live_pose_set_enabled(true); }
    }
    now_ms+=100;
    return ESP_OK;
}
static void frame(unsigned id,uint64_t time,int action)
{
    static const uint8_t raw[8]={0};
    now_ms=time; inference_action=action;
    assert(c_live_pose_submit(raw,sizeof(raw),2,2,id));
    if (!setjmp(yield_worker)) { worker_fn(NULL); }
    assert(token==1);
}
int main(void)
{
    static const uint8_t raw[8]={0};
    c_pose_event_t out={0};
    assert(!c_live_pose_is_ready());
    assert(c_live_pose_init()==ESP_OK && c_live_pose_is_ready());
    c_live_pose_set_enabled(false); now_ms=2000;
    assert(!c_live_pose_submit(raw,sizeof(raw),2,2,1));
    assert(c_live_pose_request_calibration()!=ESP_OK);
    c_live_pose_set_enabled(true);
    assert(c_live_pose_request_calibration()==ESP_OK);
    for (unsigned i=1;i<=12;i++) { frame(i,2000u*i,0); }
    assert(c_live_pose_get_latest(&out));
    assert(out.calibration_state==C_CAL_READY && out.stable_state==C_POSTURE_NEUTRAL);
    frame(13,26000,1); /* pause while the fake model is executing */
    assert(!c_live_pose_get_latest(&out));
    assert(!c_live_pose_submit(raw,sizeof(raw),2,2,14));
    c_live_pose_set_enabled(true);
    assert(!c_live_pose_get_latest(&out));
    frame(14,28000,0);
    assert(c_live_pose_get_latest(&out) && out.frame_id==14 && out.timestamp_ms==28000);
    frame(15,30000,2); /* pause+resume while a previous generation is in-flight */
    assert(!c_live_pose_get_latest(&out));
    frame(16,32000,0);
    assert(c_live_pose_get_latest(&out) && out.frame_id==16);
    now_ms=38001;
    assert(!c_live_pose_get_latest(&out));
    assert(inferences==16);
    puts("PASS: actual C live submit/pause/resume, in-flight generation rejection and 6-second expiry (fake model/RTOS)");
    return 0;
}
