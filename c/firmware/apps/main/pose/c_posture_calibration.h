#ifndef C_POSTURE_CALIBRATION_H
#define C_POSTURE_CALIBRATION_H
#include <stdbool.h>
#include <stdint.h>
#include "c_posture_filter.h"
#ifdef __cplusplus
extern "C" {
#endif

#define C_CAL_SAMPLE_COUNT 10u
typedef enum { C_CAL_IDLE, C_CAL_COLLECTING, C_CAL_READY, C_CAL_REJECTED } c_calibration_state_t;
typedef struct {
    int width,height;
    unsigned people;
    float score;
    int nose_x,nose_y,left_x,left_y,right_x,right_y;
} c_posture_landmarks_t;
typedef struct { bool valid; float angle_deg,scale; } c_posture_geometry_t;
typedef struct {
    c_calibration_state_t state;
    unsigned count;
    float angles[C_CAL_SAMPLE_COUNT],scales[C_CAL_SAMPLE_COUNT];
    float baseline_deg,baseline_scale,noise_deg,enter_deg,exit_deg,delta_deg;
    bool deviation;
} c_posture_calibration_t;

bool c_posture_geometry_make(const c_posture_landmarks_t *points,c_posture_geometry_t *out);
void c_posture_calibration_init(c_posture_calibration_t *cal);
void c_posture_calibration_start(c_posture_calibration_t *cal);
c_posture_state_t c_posture_calibration_observe(c_posture_calibration_t *cal,
                                               c_posture_geometry_t geometry);
#ifdef __cplusplus
}
#endif
#endif
