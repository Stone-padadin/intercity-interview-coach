#ifndef B_C_VISION_H
#define B_C_VISION_H
#include "b_device_state.h"

/* Call from the state owner task with full monotonic device milliseconds.
 * Reads C's actual snapshot API; never parse diagnostic serial text. */
bool b_device_poll_c_vision(b_device_state_t *state,uint64_t now_ms);
#endif
