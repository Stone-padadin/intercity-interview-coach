#include "b_c_vision.h"
#include "c_live_pose.h"

bool b_device_poll_c_vision(b_device_state_t *state,uint64_t now_ms)
{
    c_pose_event_t event={0};
    bool available=c_live_pose_get_latest(&event);
    bool raw_known=event.calibrated_raw==C_POSTURE_NEUTRAL ||
                   event.calibrated_raw==C_POSTURE_DEVIATION;
    bool usable=available && event.frame_id!=0 && event.valid && event.has_person &&
                event.error==ESP_OK && event.calibration_state==C_CAL_READY && raw_known;
    /* Keep the stable label, even when raw and stable differ during recovery.
     * Capture time is not refreshed by polling the same frame again. */
    b_device_observe_pose(state,event.stable_state,usable,event.timestamp_ms,now_ms);
    return b_device_current_pose(state,now_ms)!=C_POSTURE_UNKNOWN;
}
