#include "b_spi_workflow.h"
#include <assert.h>
#include <stdio.h>

static b_spi_sample_t sample(uint32_t frame,uint64_t time,unsigned cal,bool valid,c_posture_state_t pose)
{
    return (b_spi_sample_t){.frame_id=frame,.capture_ms=time,.calibration=cal,
        .samples=10,.usable=valid,.posture=pose};
}
int main(void)
{
    b_spi_workflow_t s;
    b_spi_workflow_init(&s,false);
    b_spi_workflow_connection(&s,true,10);
    assert(b_spi_workflow_command(&s,B_SPI_START,20)==B_SPI_ERR_UNAVAILABLE);
    assert(!s.inference_enabled);
    b_spi_workflow_init(&s,true);
    assert(s.mode==B_SPI_OFF && !s.inference_enabled);
    assert(b_spi_workflow_command(&s,B_SPI_START,20)==B_SPI_ERR_OFFLINE);
    b_spi_workflow_connection(&s,true,30);
    assert(b_spi_workflow_command(&s,B_SPI_RESUME,40)==B_SPI_ERR_START_REQUIRED);
    assert(b_spi_workflow_command(&s,B_SPI_CALIBRATE,40)==B_SPI_ERR_START_REQUIRED);
    assert(b_spi_workflow_command(&s,B_SPI_START,50)==B_SPI_OK);
    assert(s.mode==B_SPI_WAITING_BASELINE && s.inference_enabled && !s.request_calibration);
    assert(b_spi_workflow_command(&s,B_SPI_CALIBRATE,60)==B_SPI_OK);
    assert(s.request_calibration && s.mode==B_SPI_CALIBRATING);
    assert(b_spi_workflow_command(&s,B_SPI_CALIBRATE,70)==B_SPI_OK);
    assert(!s.request_calibration); /* duplicate must not restart collection */
    b_spi_workflow_observe(&s,sample(1,55,2,true,C_POSTURE_DEVIATION),80);
    assert(s.posture==C_POSTURE_UNKNOWN); /* pre-calibration in-flight frame */
    b_spi_workflow_observe(&s,sample(2,100,1,false,C_POSTURE_DEVIATION),110);
    assert(s.mode==B_SPI_CALIBRATING && s.posture==C_POSTURE_UNKNOWN);
    b_spi_workflow_observe(&s,sample(3,200,2,true,C_POSTURE_NEUTRAL),210);
    assert(s.mode==B_SPI_DETECTING && s.posture==C_POSTURE_NEUTRAL);
    b_spi_workflow_observe(&s,sample(4,300,2,true,C_POSTURE_DEVIATION),310);
    assert(s.posture==C_POSTURE_DEVIATION);
    b_spi_workflow_observe(&s,sample(4,900,2,true,C_POSTURE_NEUTRAL),910);
    assert(s.capture_ms==300); /* duplicate cannot refresh lifetime */
    b_spi_workflow_observe(&s,sample(5,250,2,true,C_POSTURE_NEUTRAL),920);
    assert(s.capture_ms==300 && s.posture==C_POSTURE_DEVIATION); /* capture time cannot regress */
    b_spi_workflow_tick(&s,6301);
    assert(s.posture==C_POSTURE_UNKNOWN);
    b_spi_workflow_observe(&s,sample(5,6500,2,false,C_POSTURE_DEVIATION),6510);
    assert(s.posture==C_POSTURE_UNKNOWN); /* occlusion or quality failure */
    b_spi_workflow_observe(&s,sample(6,6600,2,true,C_POSTURE_NEUTRAL),6610);
    assert(s.posture==C_POSTURE_NEUTRAL);
    assert(b_spi_workflow_command(&s,B_SPI_PAUSE,6700)==B_SPI_OK);
    assert(s.mode==B_SPI_PAUSED && !s.inference_enabled && s.posture==C_POSTURE_UNKNOWN);
    b_spi_workflow_observe(&s,sample(7,6800,2,true,C_POSTURE_DEVIATION),6810);
    assert(s.mode==B_SPI_PAUSED && s.posture==C_POSTURE_UNKNOWN);
    assert(b_spi_workflow_command(&s,B_SPI_CALIBRATE,6900)==B_SPI_ERR_START_REQUIRED);
    assert(b_spi_workflow_command(&s,B_SPI_RESUME,7000)==B_SPI_OK);
    b_spi_workflow_observe(&s,sample(8,6950,2,true,C_POSTURE_DEVIATION),7100);
    assert(s.posture==C_POSTURE_UNKNOWN); /* only freshly captured frames after resume */
    b_spi_workflow_observe(&s,sample(9,7200,2,true,C_POSTURE_NEUTRAL),7210);
    assert(s.posture==C_POSTURE_NEUTRAL);
    b_spi_workflow_observe(&s,sample(10,9000,2,true,C_POSTURE_DEVIATION),8000);
    assert(s.capture_ms==7200); /* future timestamp */
    assert(b_spi_workflow_command(&s,99,7300)==B_SPI_ERR_BAD_COMMAND);
    assert(b_spi_workflow_command(&s,B_SPI_QUERY,7300)==B_SPI_OK);
    assert(s.mode==B_SPI_DETECTING);
    assert(b_spi_workflow_command(&s,B_SPI_STOP,7400)==B_SPI_OK);
    assert(!s.consent && !s.inference_enabled);
    assert(b_spi_workflow_command(&s,B_SPI_RESUME,7500)==B_SPI_ERR_START_REQUIRED);
    assert(b_spi_workflow_command(&s,B_SPI_START,7600)==B_SPI_OK);
    b_spi_workflow_connection(&s,false,7700);
    b_spi_workflow_connection(&s,true,7800);
    assert(b_spi_workflow_command(&s,B_SPI_RESUME,7900)==B_SPI_ERR_START_REQUIRED);
    assert(!s.inference_enabled && s.posture==C_POSTURE_UNKNOWN);
    assert(b_spi_workflow_command(&s,B_SPI_START,8000)==B_SPI_OK);
    assert(b_spi_workflow_command(&s,B_SPI_CALIBRATE,8100)==B_SPI_OK);
    b_spi_workflow_calibration_failed(&s);
    assert(s.result==B_SPI_ERR_CALIBRATION && s.mode==B_SPI_WAITING_BASELINE);
    puts("PASS: SPI consent, calibration, pause/resume, stale/invalid/duplicate frames and reconnect");
    return 0;
}
