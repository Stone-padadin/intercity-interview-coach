#include "../stubs/yolo11_pose.h"
#include "esp_err.h"
#include <stddef.h>
typedef struct {
    yolo11_pose_frame_status_t status;
    yolo11_pose_err_type_t err_type;
    unsigned person_count;
    c_posture_geometry_t geometry;
} yolo11_pose_frame_result_t;
esp_err_t yolo11_pose_init(void);
void yolo11_pose_prealloc_buffers(void);
esp_err_t yolo11_pose_uyvy_to_rgb888(const uint8_t *raw,size_t len,uint16_t width,
    uint16_t height,uint8_t **rgb,uint16_t *out_width,uint16_t *out_height);
esp_err_t yolo11_pose_analyze_rgb888(uint8_t *rgb,uint16_t width,uint16_t height,
    const char *name,yolo11_pose_frame_result_t *result);
