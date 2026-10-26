#ifndef C_POSTURE_FILTER_H
#define C_POSTURE_FILTER_H
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef enum { C_POSTURE_UNKNOWN, C_POSTURE_NEUTRAL, C_POSTURE_DEVIATION } c_posture_state_t;
typedef struct {
    c_posture_state_t state;
    c_posture_state_t candidate;
    uint32_t candidate_count;
    uint64_t candidate_since_ms;
    uint64_t last_ms;
    bool has_sample;
} c_posture_filter_t;

/* Engineering starting values; calibrate with real hardware, not medical thresholds. */
#define C_POSTURE_HOLD_MS 1500u
#define C_POSTURE_RECOVER_MS 500u
/* Measured inference is about 2s; cover processing plus the next sampling cycle. */
#define C_POSTURE_STALE_MS 6000u

void c_posture_filter_init(c_posture_filter_t *filter);
c_posture_state_t c_posture_filter_update(c_posture_filter_t *filter,
                                         c_posture_state_t raw, uint64_t timestamp_ms);
c_posture_state_t c_posture_filter_read(const c_posture_filter_t *filter, uint64_t now_ms);
#ifdef __cplusplus
}
#endif
#endif
