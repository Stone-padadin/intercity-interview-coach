#ifndef B_DEVICE_STATE_H
#define B_DEVICE_STATE_H
#include <stdbool.h>
#include <stdint.h>
#include "c_posture_filter.h"

typedef enum { B_PREPARE, B_INTERVIEW, B_REVIEW, B_RETRY } b_device_phase_t;
typedef enum {
    B_LIGHT_OFFLINE, B_LIGHT_PREPARE, B_LIGHT_INTERVIEW, B_LIGHT_REVIEW,
    B_LIGHT_RETRY, B_LIGHT_VISION_UNKNOWN, B_LIGHT_DEVIATION
} b_device_light_t;
typedef struct { uint8_t r,g,b; } b_device_rgb_t;
typedef struct {
    b_device_phase_t phase;
    bool connected,visual_feedback_enabled,pose_valid;
    c_posture_state_t pose;
    uint64_t capture_ms;
} b_device_state_t;

/* Single-owner task API. Marshal network/UI events into that task. */
void b_device_state_init(b_device_state_t *state);
void b_device_connection_changed(b_device_state_t *state,bool connected);
bool b_device_set_phase(b_device_state_t *state,b_device_phase_t phase);
void b_device_enable_visual_feedback(b_device_state_t *state,bool enabled);
void b_device_observe_pose(b_device_state_t *state,c_posture_state_t pose,
                           bool valid,uint64_t capture_ms,uint64_t now_ms);
c_posture_state_t b_device_current_pose(const b_device_state_t *state,uint64_t now_ms);
b_device_light_t b_device_light(const b_device_state_t *state,uint64_t now_ms);
b_device_rgb_t b_device_light_rgb(b_device_light_t light);
#endif
