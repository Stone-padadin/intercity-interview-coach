#ifndef SPI_LIVE_TEST_FREERTOS_H
#define SPI_LIVE_TEST_FREERTOS_H
#include <stdint.h>
typedef void *TaskHandle_t;
typedef void *SemaphoreHandle_t;
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(lock) ((void)(lock))
#define portEXIT_CRITICAL(lock) ((void)(lock))
#define portMAX_DELAY 0xffffffffu
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(ms) (ms)
SemaphoreHandle_t xSemaphoreCreateBinary(void);
void vSemaphoreDelete(SemaphoreHandle_t sem);
int xSemaphoreTake(SemaphoreHandle_t sem,uint32_t ticks);
int xSemaphoreGive(SemaphoreHandle_t sem);
int xTaskCreatePinnedToCoreWithCaps(void (*worker)(void *),const char *name,unsigned stack,
    void *arg,unsigned priority,TaskHandle_t *handle,int core,int caps);
unsigned ulTaskNotifyTake(int clear,uint32_t ticks);
void xTaskNotifyGive(TaskHandle_t task);
void vTaskDelay(unsigned ticks);
#endif
