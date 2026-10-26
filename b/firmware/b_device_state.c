#include "b_device_state.h"

static void clear_pose(b_device_state_t *s)
{
    s->pose=C_POSTURE_UNKNOWN; s->pose_valid=false;
}
void b_device_state_init(b_device_state_t *s) { *s=(b_device_state_t){0}; }
void b_device_connection_changed(b_device_state_t *s,bool connected)
{
    if (s->connected==connected) { return; }
    s->connected=connected; s->phase=B_PREPARE;
    s->visual_feedback_enabled=false; s->capture_ms=0; clear_pose(s);
}
bool b_device_set_phase(b_device_state_t *s,b_device_phase_t phase)
{
    if (phase<B_PREPARE || phase>B_RETRY) { return false; }
    if (phase==B_PREPARE) {
        s->phase=phase; s->visual_feedback_enabled=false; s->capture_ms=0; clear_pose(s); return true;
    }
    if (!s->connected) { return false; }
    if (phase==s->phase || (s->phase==B_PREPARE && phase==B_INTERVIEW) ||
        (s->phase==B_INTERVIEW && phase==B_REVIEW) ||
        (s->phase==B_REVIEW && phase==B_RETRY) ||
        (s->phase==B_RETRY && phase==B_REVIEW)) {
        s->phase=phase; return true;
    }
    return false;
}
void b_device_enable_visual_feedback(b_device_state_t *s,bool enabled)
{
    s->visual_feedback_enabled=s->connected && enabled;
}
void b_device_observe_pose(b_device_state_t *s,c_posture_state_t pose,
                           bool valid,uint64_t capture_ms,uint64_t now_ms)
{
    if (!s->connected || !valid ||
        (pose!=C_POSTURE_NEUTRAL && pose!=C_POSTURE_DEVIATION) ||
        now_ms<capture_ms || now_ms-capture_ms>C_POSTURE_STALE_MS ||
        capture_ms<s->capture_ms) {
        clear_pose(s); return;
    }
    s->pose=pose; s->pose_valid=true; s->capture_ms=capture_ms;
}
c_posture_state_t b_device_current_pose(const b_device_state_t *s,uint64_t now_ms)
{
    if (!s->connected || !s->pose_valid || now_ms<s->capture_ms ||
        now_ms-s->capture_ms>C_POSTURE_STALE_MS) { return C_POSTURE_UNKNOWN; }
    return s->pose;
}
b_device_light_t b_device_light(const b_device_state_t *s,uint64_t now_ms)
{
    if (!s->connected) { return B_LIGHT_OFFLINE; }
    if (s->visual_feedback_enabled && (s->phase==B_INTERVIEW || s->phase==B_RETRY)) {
        c_posture_state_t pose=b_device_current_pose(s,now_ms);
        if (pose==C_POSTURE_UNKNOWN) { return B_LIGHT_VISION_UNKNOWN; }
        if (pose==C_POSTURE_DEVIATION) { return B_LIGHT_DEVIATION; }
    }
    switch (s->phase) {
    case B_INTERVIEW: return B_LIGHT_INTERVIEW;
    case B_REVIEW: return B_LIGHT_REVIEW;
    case B_RETRY: return B_LIGHT_RETRY;
    default: return B_LIGHT_PREPARE;
    }
}
b_device_rgb_t b_device_light_rgb(b_device_light_t light)
{
    /* Low-brightness starting values; supply and real LED order need bench tests. */
    static const b_device_rgb_t colors[] = {
        {24,0,0}, {0,0,24}, {0,24,0}, {20,0,20}, {0,20,20}, {8,8,8}, {24,10,0}
    };
    if (light<B_LIGHT_OFFLINE || light>B_LIGHT_DEVIATION) { return (b_device_rgb_t){0}; }
    return colors[light];
}
