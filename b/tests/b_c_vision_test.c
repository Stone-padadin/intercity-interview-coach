#include "b_c_vision.h"
#include "c_live_pose.h"
#include "c_posture_calibration.h"
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
static c_pose_event_t snapshot;
static bool getter_ok;
bool c_live_pose_get_latest(c_pose_event_t *out) { *out=snapshot; return getter_ok; }

static void good_frame(void)
{
    snapshot=(c_pose_event_t){0};
    snapshot.frame_id=1; snapshot.timestamp_ms=10000; snapshot.valid=true;
    snapshot.has_person=true; snapshot.calibration_state=C_CAL_READY;
    snapshot.calibrated_raw=C_POSTURE_NEUTRAL; snapshot.stable_state=C_POSTURE_NEUTRAL;
    getter_ok=true;
}
static void expect_unknown(b_device_state_t *s)
{
    CHECK(!b_device_poll_c_vision(s,10001));
    CHECK(b_device_light(s,10001)==B_LIGHT_VISION_UNKNOWN);
}
int main(void)
{
    b_device_state_t s; b_device_state_init(&s); b_device_connection_changed(&s,true);
    CHECK(b_device_set_phase(&s,B_INTERVIEW)); b_device_enable_visual_feedback(&s,true);
    good_frame(); CHECK(b_device_poll_c_vision(&s,10001));
    CHECK(b_device_light(&s,10001)==B_LIGHT_INTERVIEW);
    /* Legacy status/error cannot override calibrated, stable output. */
    snapshot.raw_status=YOLO11_POSE_FRAME_BAD_POSTURE;
    snapshot.raw_error=YOLO11_POSE_ERR_BODY_TILT;
    CHECK(b_device_poll_c_vision(&s,10001));
    CHECK(b_device_light(&s,10001)==B_LIGHT_INTERVIEW);
    snapshot.calibrated_raw=C_POSTURE_DEVIATION;
    CHECK(b_device_poll_c_vision(&s,10001));
    CHECK(b_device_light(&s,10001)==B_LIGHT_INTERVIEW); /* Pending C debounce. */
    snapshot.stable_state=C_POSTURE_DEVIATION;
    CHECK(b_device_poll_c_vision(&s,10001)); CHECK(b_device_light(&s,10001)==B_LIGHT_DEVIATION);
    snapshot.calibrated_raw=C_POSTURE_NEUTRAL;
    CHECK(b_device_poll_c_vision(&s,10001)); CHECK(b_device_light(&s,10001)==B_LIGHT_DEVIATION);
    CHECK(b_device_poll_c_vision(&s,16000));
    CHECK(!b_device_poll_c_vision(&s,16001)); /* Re-polling doesn't refresh capture age. */
    good_frame(); getter_ok=false; expect_unknown(&s);
    good_frame(); snapshot.valid=false; expect_unknown(&s);
    good_frame(); snapshot.frame_id=0; expect_unknown(&s);
    good_frame(); snapshot.has_person=false; expect_unknown(&s);
    good_frame(); snapshot.error=-1; expect_unknown(&s);
    good_frame(); snapshot.calibrated_raw=C_POSTURE_UNKNOWN; expect_unknown(&s);
    good_frame(); snapshot.stable_state=C_POSTURE_UNKNOWN; expect_unknown(&s);
    good_frame(); snapshot.stable_state=(c_posture_state_t)99; expect_unknown(&s);
    for (int cal=C_CAL_IDLE;cal<=C_CAL_REJECTED;cal++) {
        if (cal==C_CAL_READY) { continue; }
        good_frame(); snapshot.calibration_state=(c_calibration_state_t)cal; expect_unknown(&s);
    }

    /* Exercise C's actual calibration/filter with 2s synthetic observations. */
    c_posture_calibration_t cal; c_posture_calibration_start(&cal);
    for (unsigned i=0;i<C_CAL_SAMPLE_COUNT;i++) {
        CHECK(c_posture_calibration_observe(&cal,(c_posture_geometry_t){true,0,.5f})==C_POSTURE_UNKNOWN);
    }
    CHECK(cal.state==C_CAL_READY);
    c_posture_filter_t filter; c_posture_filter_init(&filter);
    const float angles[]={0,20,20,20,0,0};
    const b_device_light_t expected[]={B_LIGHT_INTERVIEW,B_LIGHT_INTERVIEW,B_LIGHT_INTERVIEW,
                                      B_LIGHT_DEVIATION,B_LIGHT_DEVIATION,B_LIGHT_INTERVIEW};
    for (unsigned i=0;i<6;i++) {
        good_frame(); snapshot.frame_id=i+2; snapshot.timestamp_ms=20000+2000*i;
        snapshot.calibrated_raw=c_posture_calibration_observe(&cal,(c_posture_geometry_t){true,angles[i],.5f});
        snapshot.stable_state=c_posture_filter_update(&filter,snapshot.calibrated_raw,snapshot.timestamp_ms);
        CHECK(b_device_poll_c_vision(&s,snapshot.timestamp_ms+1900));
        CHECK(b_device_light(&s,snapshot.timestamp_ms+1900)==expected[i]);
    }
    puts("PASS: C snapshot contract, every invalid gate, legacy-label rejection, capture expiry and synthetic C-to-B debounce");
    return 0;
}
