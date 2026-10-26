#ifndef C_LIVE_POSE_H
#define C_LIVE_POSE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "c_posture_filter.h"
#include "yolo11_pose.h"

typedef struct {
    uint32_t frame_id;
    uint64_t timestamp_ms; /* Capture time, not inference completion time. */
    uint32_t inference_ms;
    yolo11_pose_frame_status_t raw_status;
    yolo11_pose_err_type_t raw_error;
    c_posture_state_t stable_state;
    bool valid;
    esp_err_t error;
    bool has_person;
    c_calibration_state_t calibration_state;
    unsigned calibration_samples;
    c_posture_state_t calibrated_raw;
    float shoulder_angle_deg,shoulder_delta_deg,tilt_threshold_deg;
} c_pose_event_t;

/* Call once during boot BEFORE starting the camera or voice/cloud stack. */
esp_err_t c_live_pose_init(void);
/* Explicit neutral-reference capture. Re-run after moving the camera; RAM only. */
esp_err_t c_live_pose_request_calibration(void);
/* Task context only. Copies into owned memory; busy/rate-limited frames are dropped. */
bool c_live_pose_submit(const uint8_t *uyvy, size_t length, uint16_t width,
                        uint16_t height, uint32_t frame_id);
/* Thread-safe copy; returns false for unknown, absent, failed or expired results. */
bool c_live_pose_get_latest(c_pose_event_t *out);
#endif
