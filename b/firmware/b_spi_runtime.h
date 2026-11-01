#ifndef B_SPI_RUNTIME_H
#define B_SPI_RUNTIME_H
#include "b_device_state.h"
#include "qm_spec_api.h"
void b_spi_runtime_init(void);
void b_spi_runtime_connection(bool connected,uint64_t now_ms);
void b_spi_runtime_execute(int command,uint64_t now_ms);
void b_spi_runtime_poll(uint64_t now_ms);
b_device_light_t b_spi_runtime_light(b_device_light_t fallback);
/* Returns true only when this is our configured property; never consumes volume. */
bool b_spi_iot_handle(qm_spec_property_t *property);
#endif
