#include "c_posture_filter.h"
void c_posture_filter_init(c_posture_filter_t *f) { *f = (c_posture_filter_t){0}; }
c_posture_state_t c_posture_filter_update(c_posture_filter_t *f, c_posture_state_t raw, uint64_t ms)
{
    if (f->has_sample && ms <= f->last_ms) {
        if (ms < f->last_ms) { f->state=C_POSTURE_UNKNOWN; f->candidate_count=0; }
        return f->state;
    }
    if (f->has_sample && ms-f->last_ms > C_POSTURE_STALE_MS) {
        f->state=C_POSTURE_UNKNOWN; f->candidate_count=0;
    }
    f->last_ms=ms; f->has_sample=true;
    if (raw!=C_POSTURE_NEUTRAL && raw!=C_POSTURE_DEVIATION) {
        f->state=C_POSTURE_UNKNOWN; f->candidate_count=0;
        return f->state;
    }
    if (!f->candidate_count || f->candidate!=raw) {
        f->candidate=raw; f->candidate_since_ms=ms; f->candidate_count=1;
    } else if (f->candidate_count<3) { f->candidate_count++; }
    if (raw==C_POSTURE_NEUTRAL) {
        if (f->state!=C_POSTURE_DEVIATION ||
            (f->candidate_count>=2 && ms-f->candidate_since_ms>=C_POSTURE_RECOVER_MS)) {
            f->state=C_POSTURE_NEUTRAL;
        }
    } else if (f->candidate_count>=3 && ms-f->candidate_since_ms>=C_POSTURE_HOLD_MS) {
        f->state=C_POSTURE_DEVIATION;
    }
    return f->state;
}
c_posture_state_t c_posture_filter_read(const c_posture_filter_t *f, uint64_t ms)
{
    if (!f->has_sample || ms<f->last_ms || ms-f->last_ms>C_POSTURE_STALE_MS) {
        return C_POSTURE_UNKNOWN;
    }
    return f->state;
}
