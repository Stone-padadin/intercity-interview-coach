/* Actual runtime + explicitly fake cloud, queue and C device snapshot. */
#include "b_spi_runtime.h"
#include "b_spi_workflow.h"
#include "c_live_pose.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>

static c_pose_event_t event;
static bool enabled;
static int calibration_calls, queued_command, reports, allocations;
static int reported[7], report_error, calibration_error;
void spi_test_log(const char *tag,const char *format,...) { (void)tag; (void)format; }
void *ljyd_cloud_get_handle(void) { return (void *)1; }
bool c_live_pose_is_ready(void) { return true; }
void c_live_pose_set_enabled(bool value) { enabled=value; }
bool c_live_pose_get_latest(c_pose_event_t *out) { *out=event; return event.valid; }
esp_err_t c_live_pose_request_calibration(void) { calibration_calls++; return calibration_error; }
int b_device_runtime_spi(int command) { queued_command=command; return 0; }
qm_spec_property_t *qm_spec_property_creat(void)
{ allocations++; return calloc(1,sizeof(qm_spec_property_t)); }
int qm_spec_property_delete(qm_spec_property_t *p) { allocations--; free(p); return 0; }
qm_spec_property_operation_t *qm_spec_property_operation_creat(void)
{ allocations++; return calloc(1,sizeof(qm_spec_property_operation_t)); }
int qm_spec_property_operation_delete(qm_spec_property_operation_t *op)
{
    for (int i=0;i<op->count;i++) { qm_spec_property_delete(op->properties[i]); }
    allocations--; free(op); return 0;
}
int qm_spec_property_pack_xiid(qm_spec_property_t *p,uint8_t siid,uint16_t piid)
{ p->siid=siid; p->piid=piid; return 0; }
int qm_spec_property_pack_number(qm_spec_property_t *p,int value) { p->value=value; return 0; }
int qm_spec_property_unpack_number(qm_spec_property_t *p,int *value)
{ if (p->invalid_type) { return -1; } *value=p->value; return 0; }
int qm_spec_property_add(qm_spec_property_operation_t *op,qm_spec_property_t *p)
{ assert(op->count<6); op->properties[op->count++]=p; return 0; }
int32_t qm_iot_report(void *iot,qm_spec_property_operation_t *op)
{
    assert(iot); reports++;
    if (report_error) { return -1; } /* SDK rejects before taking ownership */
    for (int i=0;i<op->count;i++) { reported[op->properties[i]->piid]=op->properties[i]->value; }
    qm_spec_property_operation_delete(op); return 0;
}
int main(void)
{
    b_spi_runtime_init(); assert(!enabled);
    b_spi_runtime_connection(true,100);
    qm_spec_property_t p={.siid=2,.piid=1,.value=1};
    assert(!b_spi_iot_handle(&p)); /* existing volume is untouched */
    p.siid=250;
    assert(b_spi_iot_handle(&p) && queued_command==1 && !enabled);
    b_spi_runtime_execute(queued_command,200); assert(enabled);
    b_spi_runtime_poll(1200);
    assert(reported[2]==B_SPI_WAITING_BASELINE && reported[3]==C_POSTURE_UNKNOWN);
    assert(b_spi_runtime_light(B_LIGHT_PREPARE)==B_LIGHT_VISION_UNKNOWN);
    b_spi_runtime_execute(B_SPI_CALIBRATE,1300);
    b_spi_runtime_execute(B_SPI_CALIBRATE,1400);
    assert(calibration_calls==1);
    event=(c_pose_event_t){.frame_id=1,.timestamp_ms=2000,.calibration_state=C_CAL_READY,
        .calibration_samples=10,.calibrated_raw=C_POSTURE_DEVIATION,
        .stable_state=C_POSTURE_DEVIATION,.valid=true,.has_person=true,.error=ESP_OK};
    b_spi_runtime_poll(2200);
    assert(reported[2]==B_SPI_DETECTING && reported[3]==C_POSTURE_DEVIATION);
    assert(b_spi_runtime_light(B_LIGHT_REVIEW)==B_LIGHT_DEVIATION); /* independent SPI opt-in */
    event.frame_id=2; event.timestamp_ms=3000; event.has_person=false;
    b_spi_runtime_poll(3200);
    assert(reported[3]==C_POSTURE_UNKNOWN);
    assert(b_spi_runtime_light(B_LIGHT_REVIEW)==B_LIGHT_VISION_UNKNOWN);
    event.frame_id=3; event.timestamp_ms=4000; event.has_person=true;
    b_spi_runtime_poll(4200); assert(reported[3]==C_POSTURE_DEVIATION);
    b_spi_runtime_poll(10001); assert(reported[3]==C_POSTURE_UNKNOWN);
    b_spi_runtime_execute(B_SPI_PAUSE,11000); assert(!enabled);
    b_spi_runtime_poll(11200); assert(reported[2]==B_SPI_PAUSED);
    assert(b_spi_runtime_light(B_LIGHT_PREPARE)==B_LIGHT_PREPARE);
    b_spi_runtime_execute(B_SPI_RESUME,12000); assert(enabled);
    b_spi_runtime_poll(12200); assert(reported[3]==C_POSTURE_UNKNOWN);
    event.frame_id=4; event.timestamp_ms=12500; event.stable_state=C_POSTURE_NEUTRAL;
    b_spi_runtime_poll(13200); assert(reported[3]==C_POSTURE_NEUTRAL);
    calibration_error=-1;
    b_spi_runtime_execute(B_SPI_CALIBRATE,14000);
    b_spi_runtime_poll(14200); assert(reported[6]==B_SPI_ERR_CALIBRATION);
    report_error=1;
    b_spi_runtime_execute(B_SPI_QUERY,15000);
    b_spi_runtime_poll(15200); assert(allocations==0);
    report_error=0;
    b_spi_runtime_poll(16200); assert(allocations==0);
    b_spi_runtime_connection(false,17000);
    b_spi_runtime_connection(true,17100);
    b_spi_runtime_execute(B_SPI_RESUME,17200); assert(!enabled);
    b_spi_runtime_poll(18200); assert(reported[6]==B_SPI_ERR_START_REQUIRED);
    assert(allocations==0 && reports>5);
    puts("PASS: actual SPI runtime, native property dispatch, truthful shadow status and LED gates (fake hardware)");
    return 0;
}
