#include "b_device_state.h"
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)

int main(void)
{
    b_device_state_t s; b_device_state_init(&s);
    CHECK(b_device_light(&s,0)==B_LIGHT_OFFLINE);
    CHECK(!b_device_set_phase(&s,B_INTERVIEW));
    b_device_connection_changed(&s,true);
    CHECK(b_device_light(&s,0)==B_LIGHT_PREPARE);
    CHECK(!b_device_set_phase(&s,(b_device_phase_t)-1));
    CHECK(!b_device_set_phase(&s,(b_device_phase_t)4));
    CHECK(!b_device_set_phase(&s,B_REVIEW));
    CHECK(!b_device_set_phase(&s,B_RETRY));
    CHECK(b_device_set_phase(&s,B_INTERVIEW));
    CHECK(b_device_set_phase(&s,B_INTERVIEW));
    CHECK(b_device_light(&s,0)==B_LIGHT_INTERVIEW); /* Visual feedback defaults off. */
    b_device_enable_visual_feedback(&s,true);
    CHECK(b_device_light(&s,0)==B_LIGHT_VISION_UNKNOWN);
    b_device_observe_pose(&s,C_POSTURE_NEUTRAL,true,100,100);
    CHECK(b_device_light(&s,6100)==B_LIGHT_INTERVIEW);
    CHECK(b_device_light(&s,6101)==B_LIGHT_VISION_UNKNOWN);
    b_device_observe_pose(&s,C_POSTURE_DEVIATION,true,7000,7000);
    CHECK(b_device_light(&s,7001)==B_LIGHT_DEVIATION);
    CHECK(s.phase==B_INTERVIEW); /* Pose never starts review or scores an answer. */
    CHECK(b_device_set_phase(&s,B_REVIEW));
    CHECK(b_device_light(&s,7002)==B_LIGHT_REVIEW);
    CHECK(b_device_set_phase(&s,B_RETRY));
    CHECK(b_device_light(&s,7003)==B_LIGHT_DEVIATION);
    b_device_observe_pose(&s,C_POSTURE_UNKNOWN,false,8000,8000);
    CHECK(b_device_light(&s,8001)==B_LIGHT_VISION_UNKNOWN);
    b_device_observe_pose(&s,C_POSTURE_NEUTRAL,true,9000,8999);
    CHECK(b_device_current_pose(&s,8999)==C_POSTURE_UNKNOWN); /* Future capture. */
    b_device_observe_pose(&s,C_POSTURE_NEUTRAL,true,9000,9000);
    b_device_observe_pose(&s,C_POSTURE_DEVIATION,true,8999,9001);
    CHECK(b_device_current_pose(&s,9001)==C_POSTURE_UNKNOWN); /* Reordered sample. */
    b_device_observe_pose(&s,C_POSTURE_DEVIATION,true,8999,9002);
    CHECK(b_device_current_pose(&s,9002)==C_POSTURE_UNKNOWN); /* Repeated old input stays unknown. */
    b_device_observe_pose(&s,C_POSTURE_NEUTRAL,true,9003,9003);
    CHECK(b_device_current_pose(&s,9003)==C_POSTURE_NEUTRAL);
    b_device_connection_changed(&s,false);
    CHECK(s.phase==B_PREPARE && !s.visual_feedback_enabled);
    CHECK(b_device_light(&s,10000)==B_LIGHT_OFFLINE);
    b_device_enable_visual_feedback(&s,true);
    CHECK(!s.visual_feedback_enabled);
    b_device_connection_changed(&s,true);
    CHECK(s.phase==B_PREPARE && !s.pose_valid);
    CHECK(b_device_set_phase(&s,B_INTERVIEW));
    b_device_enable_visual_feedback(&s,true);
    CHECK(b_device_set_phase(&s,B_PREPARE));
    CHECK(!s.visual_feedback_enabled);
    b_device_observe_pose(&s,C_POSTURE_NEUTRAL,true,UINT64_C(0x100000010),UINT64_C(0x100000011));
    CHECK(b_device_current_pose(&s,UINT64_C(0x100000012))==C_POSTURE_NEUTRAL);
    b_device_rgb_t unknown=b_device_light_rgb(B_LIGHT_VISION_UNKNOWN);
    CHECK(unknown.r==unknown.g && unknown.g==unknown.b);
    puts("PASS: B phases, visual opt-in, invalid/stale/reordered data, disconnect recovery and 64-bit time");
    return 0;
}
