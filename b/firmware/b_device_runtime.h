#ifndef B_DEVICE_RUNTIME_H
#define B_DEVICE_RUNTIME_H
#include <stdbool.h>
#include "b_device_state.h"

/* Start once after qm_work/bsp_io and before cloud callbacks can fire. */
int b_device_runtime_init(void);
/* Task-context, nonblocking handoff from the actual cloud callback. */
void b_device_runtime_cloud(bool connected);
/* Local product entry points. No network API or platform property is implied. */
int b_device_runtime_phase(b_device_phase_t phase);
int b_device_runtime_visual(bool enabled);
#endif
