/* Host tests only. No model, camera, inference or hardware implementation. */
#ifndef B_TEST_YOLO11_POSE_H
#define B_TEST_YOLO11_POSE_H
#include "c_posture_calibration.h"
typedef enum { YOLO11_POSE_FRAME_NO_PERSON, YOLO11_POSE_FRAME_OK,
               YOLO11_POSE_FRAME_BAD_POSTURE, YOLO11_POSE_FRAME_UNKNOWN } yolo11_pose_frame_status_t;
typedef enum { YOLO11_POSE_ERR_NONE, YOLO11_POSE_ERR_YAW,
               YOLO11_POSE_ERR_BODY_TILT, YOLO11_POSE_ERR_TOO_CLOSE,
               YOLO11_POSE_ERR_HEAD_DOWN } yolo11_pose_err_type_t;
#endif
