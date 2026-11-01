#ifndef B_SPI_WORKFLOW_H
#define B_SPI_WORKFLOW_H
#include <stdbool.h>
#include <stdint.h>
#include "c_posture_filter.h"

/* Local contract; platform xiids are supplied from an actual product export. */
typedef enum {
    B_SPI_OFF, B_SPI_WAITING_BASELINE, B_SPI_CALIBRATING,
    B_SPI_DETECTING, B_SPI_PAUSED, B_SPI_UNAVAILABLE
} b_spi_mode_t;
typedef enum {
    B_SPI_START=1, B_SPI_CALIBRATE, B_SPI_PAUSE, B_SPI_RESUME,
    B_SPI_STOP, B_SPI_QUERY
} b_spi_command_t;
typedef enum {
    B_SPI_OK, B_SPI_ERR_UNAVAILABLE, B_SPI_ERR_OFFLINE,
    B_SPI_ERR_START_REQUIRED, B_SPI_ERR_BAD_COMMAND, B_SPI_ERR_CALIBRATION
} b_spi_result_t;
typedef struct {
    uint32_t frame_id;
    uint64_t capture_ms;
    unsigned calibration, samples;
    bool usable;
    c_posture_state_t posture;
} b_spi_sample_t;
typedef struct {
    b_spi_mode_t mode;
    bool available, connected, consent, paused;
    bool inference_enabled, request_calibration;
    unsigned calibration, samples;
    c_posture_state_t posture;
    b_spi_result_t result;
    uint32_t last_frame_id;
    uint64_t capture_ms, accept_after_ms;
} b_spi_workflow_t;

void b_spi_workflow_init(b_spi_workflow_t *s,bool available);
void b_spi_workflow_connection(b_spi_workflow_t *s,bool connected,uint64_t now_ms);
b_spi_result_t b_spi_workflow_command(b_spi_workflow_t *s,int command,uint64_t now_ms);
void b_spi_workflow_calibration_failed(b_spi_workflow_t *s);
void b_spi_workflow_observe(b_spi_workflow_t *s,b_spi_sample_t sample,uint64_t now_ms);
void b_spi_workflow_tick(b_spi_workflow_t *s,uint64_t now_ms);
#endif
