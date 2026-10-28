#include "c_live_pose.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "qm_cli.h"
#include <inttypes.h>
#include <string.h>

#define RAW_CAPACITY (240u * 320u * 2u)
#define INFERENCE_INTERVAL_MS 1000u
static const char *TAG="c_live_pose";
static uint8_t *s_raw;
static SemaphoreHandle_t s_free;
static TaskHandle_t s_worker;
static uint16_t s_width, s_height;
static uint32_t s_frame_id;
static uint64_t s_captured_ms, s_last_submit_ms;
static bool s_has_submit;
static c_posture_filter_t s_filter;
static c_posture_calibration_t s_calibration;
static bool s_calibration_requested;
static c_pose_event_t s_latest;
static portMUX_TYPE s_result_lock=portMUX_INITIALIZER_UNLOCKED;

static void pose_worker(void *arg)
{
    (void)arg;
    for (;;) {
        ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
        portENTER_CRITICAL(&s_result_lock);
        bool calibrate=s_calibration_requested;
        s_calibration_requested=false;
        portEXIT_CRITICAL(&s_result_lock);
        if (calibrate) {
            c_posture_calibration_start(&s_calibration);
            c_posture_filter_init(&s_filter);
        }
        uint8_t *rgb=NULL;
        uint16_t width=0,height=0;
        yolo11_pose_frame_result_t result={.status=YOLO11_POSE_FRAME_UNKNOWN};
        int64_t started=esp_timer_get_time();
        esp_err_t err;
#if CONFIG_C_POSE_ROTATE_CW90
        err=yolo11_pose_uyvy_to_rgb888_cw90(s_raw,
            (size_t)s_width*s_height*2,s_width,s_height,&rgb,&width,&height);
#else
        err=yolo11_pose_uyvy_to_rgb888(s_raw,
            (size_t)s_width*s_height*2,s_width,s_height,&rgb,&width,&height);
#endif
        if (err==ESP_OK) { err=yolo11_pose_analyze_rgb888(rgb,width,height,"live-camera",&result); }
        c_pose_event_t event={
            .frame_id=s_frame_id,.timestamp_ms=s_captured_ms,
            .inference_ms=(uint32_t)((esp_timer_get_time()-started)/1000),
            .raw_status=result.status,.raw_error=result.err_type,.error=err
        };
        uint64_t completed_ms=(uint64_t)(esp_timer_get_time()/1000);
        bool fresh=completed_ms-event.timestamp_ms<=C_POSTURE_STALE_MS;
        event.has_person=err==ESP_OK && fresh && result.person_count>0;
        c_posture_geometry_t geometry=result.geometry;
        if (err!=ESP_OK || !fresh) { geometry.valid=false; }
        c_posture_state_t raw=c_posture_calibration_observe(&s_calibration,geometry);
        event.calibrated_raw=raw;
        event.calibration_state=s_calibration.state;
        event.calibration_samples=s_calibration.count;
        event.shoulder_angle_deg=geometry.angle_deg;
        event.shoulder_delta_deg=s_calibration.delta_deg;
        event.tilt_threshold_deg=s_calibration.enter_deg;
        event.stable_state=c_posture_filter_update(&s_filter,raw,event.timestamp_ms);
        event.valid=raw!=C_POSTURE_UNKNOWN && event.stable_state!=C_POSTURE_UNKNOWN;
        portENTER_CRITICAL(&s_result_lock);
        if (s_calibration_requested) {
            event.valid=false; event.stable_state=C_POSTURE_UNKNOWN;
            event.calibration_state=C_CAL_COLLECTING; event.calibration_samples=0;
        }
        s_latest=event;
        portEXIT_CRITICAL(&s_result_lock);
        /* ROM nano printf cannot consume 64-bit formats. Keep full precision in the event. */
        ESP_LOGI(TAG,"CPOSE frame=%" PRIu32 " capture_ms=%" PRIu32
                 " infer_ms=%" PRIu32 " status=%d error=%d stable=%d valid=%d"
                 " err=%d internal=%u psram=%u",
                 event.frame_id,(uint32_t)event.timestamp_ms,event.inference_ms,
                 (int)event.raw_status,(int)event.raw_error,(int)event.stable_state,
                 event.valid,(int)event.error,
                 (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),
                 (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
        ESP_LOGI(TAG,"CCAL frame=%" PRIu32 " people=%d state=%d samples=%u raw=%d stable=%d"
                 " valid=%d angle_md=%d delta_md=%d base_md=%d enter_md=%d noise_md=%d",
                 event.frame_id,event.has_person,(int)event.calibration_state,
                 event.calibration_samples,(int)event.calibrated_raw,(int)event.stable_state,
                 event.valid,(int)(event.shoulder_angle_deg*1000),
                 (int)(event.shoulder_delta_deg*1000),(int)(s_calibration.baseline_deg*1000),
                 (int)(s_calibration.enter_deg*1000),(int)(s_calibration.noise_deg*1000));
        xSemaphoreGive(s_free);
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

esp_err_t c_live_pose_request_calibration(void)
{
    if (!s_worker) { return ESP_ERR_INVALID_STATE; }
    portENTER_CRITICAL(&s_result_lock);
    s_calibration_requested=true;
    s_latest.valid=false; s_latest.stable_state=C_POSTURE_UNKNOWN;
    s_latest.calibration_state=C_CAL_COLLECTING; s_latest.calibration_samples=0;
    portEXIT_CRITICAL(&s_result_lock);
    ESP_LOGI(TAG,"CCAL requested: hold neutral for %u valid frames",C_CAL_SAMPLE_COUNT);
    return ESP_OK;
}

static void posecal_command(char *out,int length,int argc,char **argv)
{
    (void)out; (void)length; (void)argc; (void)argv;
    (void)c_live_pose_request_calibration();
}
static const struct qm_cli_command s_posecal_command={
    .name="posecal",.help="Capture a fixed-camera neutral shoulder reference",.function=posecal_command
};

esp_err_t c_live_pose_init(void)
{
    if (s_worker) { return ESP_OK; }
    esp_err_t err=yolo11_pose_init();
    if (err!=ESP_OK) { return err; }
    yolo11_pose_prealloc_buffers();
    s_raw=heap_caps_malloc(RAW_CAPACITY,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    s_free=xSemaphoreCreateBinary();
    if (!s_raw || !s_free) {
        if (s_free) { vSemaphoreDelete(s_free); s_free=NULL; }
        heap_caps_free(s_raw); s_raw=NULL;
        return ESP_ERR_NO_MEM;
    }
    c_posture_filter_init(&s_filter);
    c_posture_calibration_init(&s_calibration);
    if (xTaskCreatePinnedToCoreWithCaps(pose_worker,"c_pose",16*1024,NULL,3,
            &s_worker,1,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)!=pdPASS) {
        vSemaphoreDelete(s_free); s_free=NULL;
        heap_caps_free(s_raw); s_raw=NULL;
        return ESP_ERR_NO_MEM;
    }
    xSemaphoreGive(s_free);
    if (qm_cli_register_command(&s_posecal_command)!=0) {
        ESP_LOGE(TAG,"posecal CLI registration failed");
        return ESP_FAIL;
    }
    ESP_LOGI(TAG,"ready: single owned UYVY frame, interval=%u ms, rotate_cw90=%d",
             INFERENCE_INTERVAL_MS,CONFIG_C_POSE_ROTATE_CW90);
    return ESP_OK;
}

bool c_live_pose_submit(const uint8_t *uyvy,size_t length,uint16_t width,
                        uint16_t height,uint32_t frame_id)
{
    size_t expected=(size_t)width*height*2;
    if (!s_worker || !uyvy || !width || !height || (width&1u) ||
        expected>RAW_CAPACITY || length!=expected) { return false; }
    uint64_t now=(uint64_t)(esp_timer_get_time()/1000);
    if (s_has_submit && now-s_last_submit_ms<INFERENCE_INTERVAL_MS) { return false; }
    if (xSemaphoreTake(s_free,0)!=pdTRUE) { return false; }
    memcpy(s_raw,uyvy,length);
    s_width=width; s_height=height; s_frame_id=frame_id; s_captured_ms=now;
    s_last_submit_ms=now; s_has_submit=true;
    xTaskNotifyGive(s_worker);
    return true;
}

bool c_live_pose_get_latest(c_pose_event_t *out)
{
    if (!out) { return false; }
    portENTER_CRITICAL(&s_result_lock);
    *out=s_latest;
    portEXIT_CRITICAL(&s_result_lock);
    uint64_t now=(uint64_t)(esp_timer_get_time()/1000);
    if (!out->frame_id || now<out->timestamp_ms || now-out->timestamp_ms>C_POSTURE_STALE_MS) {
        out->valid=false; out->has_person=false; out->stable_state=C_POSTURE_UNKNOWN;
    }
    return out->valid;
}
