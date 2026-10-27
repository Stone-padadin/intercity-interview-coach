#include "b_device_runtime.h"
#include "qm.h"
#include "qm_cli.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <string.h>
#if CONFIG_C_LIVE_POSE_SUPPORT
#include "b_c_vision.h"
#endif
#if CONFIG_B_DEVICE_LED_SUPPORT
#include "bsp_ws2812.h"
#endif

#define TAG "b_device"
typedef enum { B_CMD_STATUS,B_CMD_PHASE,B_CMD_VISUAL,B_CMD_LED_TEST } b_command_t;
typedef struct { b_command_t command; int value; } b_message_t;
static QueueHandle_t s_commands,s_network;
static TaskHandle_t s_task;

static int enqueue(b_command_t command,int value)
{
    b_message_t message={command,value};
    if (!s_commands) { return -QM_EINIT; }
    return xQueueSend(s_commands,&message,0)==pdTRUE ? QM_EOK : -QM_EBUSY;
}
int b_device_runtime_phase(b_device_phase_t phase)
{
    if (phase<B_PREPARE || phase>B_RETRY) { return -QM_EINVAL; }
    return enqueue(B_CMD_PHASE,(int)phase);
}
int b_device_runtime_visual(bool enabled) { return enqueue(B_CMD_VISUAL,enabled); }
void b_device_runtime_cloud(bool connected)
{
    if (s_network) { (void)xQueueOverwrite(s_network,&connected); }
}
static void cli(char *out,int length,int argc,char **argv)
{
    (void)out; (void)length;
    int ret=-QM_EINVAL;
    if (argc==2 && strcmp(argv[1],"status")==0) { ret=enqueue(B_CMD_STATUS,0); }
    if (argc==3 && strcmp(argv[1],"phase")==0) {
        static const char *names[]={"prepare","interview","review","retry"};
        for (int i=0;i<4;i++) {
            if (strcmp(argv[2],names[i])==0) { ret=b_device_runtime_phase((b_device_phase_t)i); }
        }
    }
    if (argc==3 && strcmp(argv[1],"visual")==0) {
        if (strcmp(argv[2],"on")==0) { ret=b_device_runtime_visual(true); }
        if (strcmp(argv[2],"off")==0) { ret=b_device_runtime_visual(false); }
    }
    if (argc==3 && strcmp(argv[1],"led")==0 && strcmp(argv[2],"test")==0) {
        ret=enqueue(B_CMD_LED_TEST,0);
    }
    QM_LOGI(TAG,"LOCAL_CLI queued ret=%d; b status | b phase prepare/interview/review/retry | b visual on/off | b led test",ret);
}
static const struct qm_cli_command s_cli={"b","Device status and local diagnostic controls",cli};
static void status(const b_device_state_t *state,uint64_t now)
{
    QM_LOGI(TAG,"status online=%d phase=%d visual=%d pose=%d led_enabled=%d internal=%u largest=%u psram=%u",
        state->connected,(int)state->phase,state->visual_feedback_enabled,
        (int)b_device_current_pose(state,now),CONFIG_B_DEVICE_LED_SUPPORT,
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
}
static void worker(void *arg)
{
    (void)arg;
    b_device_state_t state; b_device_state_init(&state);
    int old_light=-1;
    uint64_t last_status=0;
#if CONFIG_B_DEVICE_LED_SUPPORT
    bool led_ready=bsp_ws2812_init()==QM_EOK;
    QM_LOGI(TAG,"LED hardware initialized=%d",led_ready);
#endif
    for (;;) {
        uint64_t now=(uint64_t)(esp_timer_get_time()/1000);
        bool connected;
        if (xQueueReceive(s_network,&connected,0)==pdTRUE) {
            /* Even a fast disconnect/reconnect starts a fresh local session. */
            b_device_connection_changed(&state,false);
            b_device_connection_changed(&state,connected);
            xQueueReset(s_commands);
            QM_LOGI(TAG,"actual cloud connected=%d; confirm project and visual option again",connected);
        }
        b_message_t message;
        while (xQueueReceive(s_commands,&message,0)==pdTRUE) {
            if (message.command==B_CMD_PHASE) {
                bool accepted=b_device_set_phase(&state,(b_device_phase_t)message.value);
                QM_LOGI(TAG,"phase request=%d accepted=%d actual=%d",message.value,accepted,(int)state.phase);
            } else if (message.command==B_CMD_VISUAL) {
                b_device_enable_visual_feedback(&state,message.value!=0);
                QM_LOGI(TAG,"visual enabled=%d",state.visual_feedback_enabled);
            } else if (message.command==B_CMD_LED_TEST) {
#if CONFIG_B_DEVICE_LED_SUPPORT
                const uint8_t colors[][3]={{24,0,0},{0,24,0},{0,0,24}};
                for (unsigned i=0;i<3 && led_ready;i++) {
                    int ret=bsp_ws2812_fill(colors[i][0],colors[i][1],colors[i][2]);
                    QM_LOGI(TAG,"LOCAL_LED_TEST color=%u hardware_ret=%d; not platform evidence",i,ret);
                    vTaskDelay(pdMS_TO_TICKS(500));
                }
                old_light=-1;
#else
                QM_LOGW(TAG,"LED hardware disabled in this build; no light test performed");
#endif
            } else { status(&state,now); }
        }
#if CONFIG_C_LIVE_POSE_SUPPORT
        (void)b_device_poll_c_vision(&state,now);
#endif
        int light=(int)b_device_light(&state,now);
        if (light!=old_light) {
            b_device_rgb_t rgb=b_device_light_rgb((b_device_light_t)light);
            QM_LOGI(TAG,"desired_light=%d rgb=%u,%u,%u",light,rgb.r,rgb.g,rgb.b);
#if CONFIG_B_DEVICE_LED_SUPPORT
            if (led_ready && bsp_ws2812_fill(rgb.r,rgb.g,rgb.b)!=QM_EOK) {
                QM_LOGE(TAG,"LED write failed");
            }
#endif
            old_light=light;
        }
        if (!last_status || now-last_status>=15000) { status(&state,now); last_status=now; }
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}
int b_device_runtime_init(void)
{
    if (s_task) { return QM_EOK; }
    s_commands=xQueueCreate(8,sizeof(b_message_t));
    s_network=xQueueCreate(1,sizeof(bool));
    if (!s_commands || !s_network) { goto fail; }
    if (xTaskCreatePinnedToCoreWithCaps(worker,"b_device",4096,NULL,3,&s_task,0,
                                     MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)!=pdPASS) { goto fail; }
    if (qm_cli_register_command(&s_cli)!=0) { QM_LOGW(TAG,"CLI registration failed"); }
    QM_LOGI(TAG,"runtime started; visual defaults off; no implicit cloud workflow");
    return QM_EOK;
fail:
    if (s_commands) { vQueueDelete(s_commands); }
    if (s_network) { vQueueDelete(s_network); }
    s_commands=NULL; s_network=NULL; s_task=NULL;
    return -QM_ENOMEM;
}
