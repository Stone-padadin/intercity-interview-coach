#include "b_spi_workflow.h"

static void clear_pose(b_spi_workflow_t *s,uint64_t now)
{
    s->posture=C_POSTURE_UNKNOWN;
    s->capture_ms=0;
    s->accept_after_ms=now;
}
void b_spi_workflow_init(b_spi_workflow_t *s,bool available)
{
    *s=(b_spi_workflow_t){.available=available,
        .mode=available?B_SPI_OFF:B_SPI_UNAVAILABLE};
}
void b_spi_workflow_connection(b_spi_workflow_t *s,bool connected,uint64_t now)
{
    s->connected=connected;
    s->consent=false; s->paused=false;
    s->inference_enabled=false; s->request_calibration=false;
    s->mode=s->available?B_SPI_OFF:B_SPI_UNAVAILABLE;
    clear_pose(s,now);
}
b_spi_result_t b_spi_workflow_command(b_spi_workflow_t *s,int cmd,uint64_t now)
{
    s->request_calibration=false;
    s->result=B_SPI_OK;
    if (cmd<B_SPI_START || cmd>B_SPI_QUERY) { return s->result=B_SPI_ERR_BAD_COMMAND; }
    if (cmd==B_SPI_QUERY) { return s->result; }
    /* Stop/pause remain possible even when the device has lost connectivity. */
    if (cmd==B_SPI_STOP || cmd==B_SPI_PAUSE) {
        s->inference_enabled=false; clear_pose(s,now);
        if (cmd==B_SPI_STOP) { s->consent=false; s->paused=false; }
        else if (s->consent) { s->paused=true; }
        s->mode=!s->available?B_SPI_UNAVAILABLE:(s->paused?B_SPI_PAUSED:B_SPI_OFF);
        return s->result;
    }
    if (!s->available) { return s->result=B_SPI_ERR_UNAVAILABLE; }
    if (!s->connected) { return s->result=B_SPI_ERR_OFFLINE; }
    if (cmd==B_SPI_START) {
        if (s->consent && !s->paused) { return s->result; }
        s->consent=true; s->paused=false; s->inference_enabled=true;
        s->mode=B_SPI_WAITING_BASELINE; clear_pose(s,now);
    } else if (cmd==B_SPI_RESUME) {
        if (!s->consent) { return s->result=B_SPI_ERR_START_REQUIRED; }
        if (!s->paused) { return s->result; }
        s->paused=false; s->inference_enabled=true;
        s->mode=B_SPI_WAITING_BASELINE; clear_pose(s,now);
    } else if (cmd==B_SPI_CALIBRATE) {
        if (!s->consent || s->paused) { return s->result=B_SPI_ERR_START_REQUIRED; }
        /* A repeated command during collection must not reset the 10 samples. */
        if (s->mode==B_SPI_CALIBRATING) { return s->result; }
        s->calibration=1; s->samples=0;
        s->mode=B_SPI_CALIBRATING; s->request_calibration=true;
        clear_pose(s,now);
    }
    return s->result;
}
void b_spi_workflow_calibration_failed(b_spi_workflow_t *s)
{
    s->request_calibration=false; s->calibration=0; s->samples=0;
    s->posture=C_POSTURE_UNKNOWN; s->mode=B_SPI_WAITING_BASELINE;
    s->result=B_SPI_ERR_CALIBRATION;
}
void b_spi_workflow_tick(b_spi_workflow_t *s,uint64_t now)
{
    if (!s->connected || !s->consent || s->paused || !s->capture_ms ||
        now<s->capture_ms || now-s->capture_ms>C_POSTURE_STALE_MS) {
        s->posture=C_POSTURE_UNKNOWN;
    }
}
void b_spi_workflow_observe(b_spi_workflow_t *s,b_spi_sample_t e,uint64_t now)
{
    b_spi_workflow_tick(s,now);
    if (!s->connected || !s->consent || s->paused || !s->inference_enabled) { return; }
    if (!e.frame_id || e.frame_id<=s->last_frame_id ||
        e.capture_ms<s->accept_after_ms || e.capture_ms<s->capture_ms || e.capture_ms>now ||
        now-e.capture_ms>C_POSTURE_STALE_MS) { return; }
    s->last_frame_id=e.frame_id; s->capture_ms=e.capture_ms;
    s->calibration=e.calibration; s->samples=e.samples;
    if (e.calibration==1) { s->mode=B_SPI_CALIBRATING; }
    else if (e.calibration==2) { s->mode=B_SPI_DETECTING; }
    else { s->mode=B_SPI_WAITING_BASELINE; }
    s->posture=e.usable && e.calibration==2 &&
        (e.posture==C_POSTURE_NEUTRAL || e.posture==C_POSTURE_DEVIATION)
        ?e.posture:C_POSTURE_UNKNOWN;
}
