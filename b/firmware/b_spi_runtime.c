#include "b_spi_runtime.h"
#include "b_spi_workflow.h"
#include "b_device_runtime.h"
#include "ljyd_cloud.h"
#include "qm.h"
#include "qm_iot_api.h"
#include "b_spi_mapping.h"
#if CONFIG_C_LIVE_POSE_SUPPORT
#include "c_live_pose.h"
#endif

static b_spi_workflow_t s_state;
static bool s_dirty;
static uint64_t s_last_report;
#define TAG "b_spi"

void b_spi_runtime_init(void)
{
    bool available=false;
#if CONFIG_C_LIVE_POSE_SUPPORT
    available=c_live_pose_is_ready();
    c_live_pose_set_enabled(false);
#endif
    b_spi_workflow_init(&s_state,available);
}
void b_spi_runtime_connection(bool connected,uint64_t now)
{
    b_spi_workflow_connection(&s_state,connected,now);
#if CONFIG_C_LIVE_POSE_SUPPORT
    c_live_pose_set_enabled(false);
#endif
    s_dirty=true;
}
void b_spi_runtime_execute(int cmd,uint64_t now)
{
    (void)b_spi_workflow_command(&s_state,cmd,now);
#if CONFIG_C_LIVE_POSE_SUPPORT
    c_live_pose_set_enabled(s_state.inference_enabled);
    if (s_state.request_calibration) {
        if (c_live_pose_request_calibration()!=ESP_OK) {
            b_spi_workflow_calibration_failed(&s_state);
        }
        s_state.request_calibration=false;
    }
#endif
    QM_LOGI(TAG,"command=%d result=%d mode=%d; queued does not mean calibration complete",
            cmd,(int)s_state.result,(int)s_state.mode);
    s_dirty=true;
}
static bool add_number(qm_spec_property_operation_t *op,unsigned piid,int value)
{
    qm_spec_property_t *p=qm_spec_property_creat();
    if (!p) { return false; }
    if (qm_spec_property_pack_xiid(p,B_SPI_SIID,(uint16_t)piid)!=QM_EOK ||
        qm_spec_property_pack_number(p,value)!=QM_EOK ||
        qm_spec_property_add(op,p)!=QM_EOK) {
        qm_spec_property_delete(p); return false;
    }
    return true;
}
static bool report(void)
{
    if (!B_SPI_MAPPING_ENABLED || !s_state.connected) { return false; }
    void *iot=ljyd_cloud_get_handle();
    if (!iot) { return false; }
    qm_spec_property_operation_t *op=qm_spec_property_operation_creat();
    if (!op) { return false; }
    bool ok=add_number(op,B_SPI_STATE_PIID,(int)s_state.mode) &&
        add_number(op,B_SPI_POSE_PIID,(int)s_state.posture) &&
        add_number(op,B_SPI_CALIBRATION_PIID,(int)s_state.calibration) &&
        add_number(op,B_SPI_SAMPLES_PIID,(int)s_state.samples) &&
        add_number(op,B_SPI_RESULT_PIID,(int)s_state.result);
    if (!ok || qm_iot_report(iot,op)!=QM_EOK) {
        qm_spec_property_operation_delete(op); return false;
    }
    return true;
}
void b_spi_runtime_poll(uint64_t now)
{
    b_spi_mode_t old_mode=s_state.mode;
    c_posture_state_t old_pose=s_state.posture;
    unsigned old_cal=s_state.calibration,old_samples=s_state.samples;
#if CONFIG_C_LIVE_POSE_SUPPORT
    c_pose_event_t e={0};
    bool available=c_live_pose_get_latest(&e);
    bool raw=e.calibrated_raw==C_POSTURE_NEUTRAL || e.calibrated_raw==C_POSTURE_DEVIATION;
    bool valid=available && e.valid && e.has_person && e.error==ESP_OK && raw;
    b_spi_workflow_observe(&s_state,(b_spi_sample_t){
        .frame_id=e.frame_id,.capture_ms=e.timestamp_ms,
        .calibration=(unsigned)e.calibration_state,.samples=e.calibration_samples,
        .usable=valid,.posture=e.stable_state},now);
#endif
    b_spi_workflow_tick(&s_state,now);
    if (old_mode!=s_state.mode || old_pose!=s_state.posture ||
        old_cal!=s_state.calibration || old_samples!=s_state.samples) { s_dirty=true; }
    if ((s_dirty && now-s_last_report>=1000) || now-s_last_report>=15000) {
        QM_LOGI(TAG,"SPI_STATUS mode=%d posture=%d cal=%u samples=%u result=%d frames=%u; physical output unverified",
            (int)s_state.mode,(int)s_state.posture,s_state.calibration,s_state.samples,
            (int)s_state.result,(unsigned)s_state.last_frame_id);
        s_dirty=!report(); s_last_report=now;
    }
}
b_device_light_t b_spi_runtime_light(b_device_light_t fallback)
{
    /* Explicit SPI consent has its own gate, independent of old interview names.
     * We do not change an experiment phase just to get an orange light. */
    if (!s_state.connected || !s_state.consent || s_state.paused) { return fallback; }
    if (s_state.posture==C_POSTURE_UNKNOWN) { return B_LIGHT_VISION_UNKNOWN; }
    return s_state.posture==C_POSTURE_DEVIATION?B_LIGHT_DEVIATION:B_LIGHT_INTERVIEW;
}
bool b_spi_iot_handle(qm_spec_property_t *property)
{
    if (!B_SPI_MAPPING_ENABLED || !property || property->siid!=B_SPI_SIID ||
        property->piid!=B_SPI_COMMAND_PIID) { return false; }
    int cmd=0;
    if (qm_spec_property_unpack_number(property,&cmd)!=QM_EOK) {
        QM_LOGW(TAG,"invalid command property type"); return true;
    }
    int ret=b_device_runtime_spi(cmd);
    QM_LOGI(TAG,"platform command=%d enqueue=%d; execution reported by B worker",cmd,ret);
    return true;
}
