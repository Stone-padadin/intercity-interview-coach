#include "b_lab.h"
#include "qm.h"
#include "qm_cli.h"
#include "qm_agent_event.h"
#include "agent_app.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "cJSON.h"
#include <string.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define TEXT_LIMIT 64
#define ID_LIMIT 64
typedef struct { char experiment[ID_LIMIT+1]; unsigned epoch; int mode; } context_t;
typedef struct { context_t context; uint64_t time; int kind; qm_agent_event_notice_t notice; } event_t;
typedef struct { context_t context; unsigned cancellation; uint64_t deadline; char id[33]; char text[TEXT_LIMIT+1]; } speech_t;
static context_t s_context;
static char s_boot[17];
static uint32_t s_seq;
static unsigned s_cancel, s_drops;
static int s_busy, s_started, s_complete, s_failed, s_ambiguous;
static uint32_t s_play_generation;
static int s_dialog;
static QueueHandle_t s_events, s_speech;
static SemaphoreHandle_t s_print;
static portMUX_TYPE s_lock=portMUX_INITIALIZER_UNLOCKED;
static const char *s_modes[]={"prepare","record","analysis","review","paused","ended"};

static uint64_t now_ms(void) { return (uint64_t)(esp_timer_get_time()/1000); }
static context_t context(void) {
    context_t value;
    portENTER_CRITICAL(&s_lock); value=s_context; portEXIT_CRITICAL(&s_lock);
    return value;
}
static int identifier(const char *s, size_t max) {
    size_t n=strlen(s);
    if (!n || n>max) return 0;
    for (size_t i=0;i<n;i++)
        if (!((s[i]>='a'&&s[i]<='z')||(s[i]>='A'&&s[i]<='Z')||
              (s[i]>='0'&&s[i]<='9')||s[i]=='_'||s[i]=='-')) return 0;
    return 1;
}
/* Find complete UTF-8 prefix; a truncated SDK snapshot may end inside a codepoint. */
static size_t utf8_prefix(const char *s, size_t n) {
    size_t i=0;
    while (i<n) {
        unsigned char a=(unsigned char)s[i]; size_t count;
        if (a<0x80) count=1;
        else if (a>=0xc2&&a<=0xdf) count=2;
        else if (a>=0xe0&&a<=0xef) count=3;
        else if (a>=0xf0&&a<=0xf4) count=4;
        else break;
        if (i+count>n) break;
        int ok=1;
        for (size_t j=1;j<count;j++) if (((unsigned char)s[i+j]&0xc0)!=0x80) ok=0;
        if (count>=3 && ((a==0xe0&&(unsigned char)s[i+1]<0xa0)||
            (a==0xed&&(unsigned char)s[i+1]>=0xa0))) ok=0;
        if (count==4 && ((a==0xf0&&(unsigned char)s[i+1]<0x90)||
            (a==0xf4&&(unsigned char)s[i+1]>=0x90))) ok=0;
        if (!ok) break;
        i+=count;
    }
    return i;
}
static void emit(const context_t *ctx, uint64_t at, const char *kind, cJSON *data) {
    cJSON *root=cJSON_CreateObject();
    if (!root || !data) { cJSON_Delete(root); cJSON_Delete(data); return; }
    xSemaphoreTake(s_print,portMAX_DELAY);
    char id[40]; snprintf(id,sizeof(id),"%s-%lu",s_boot,(unsigned long)++s_seq);
    cJSON_AddStringToObject(root,"schema","b.lab.v1");
    cJSON_AddStringToObject(root,"event_id",id);
    cJSON_AddStringToObject(root,"boot_id",s_boot);
    cJSON_AddNumberToObject(root,"seq",s_seq);
    cJSON_AddNumberToObject(root,"device_ms",(double)at);
    cJSON_AddStringToObject(root,"experiment_id",ctx->experiment);
    cJSON_AddStringToObject(root,"phase",s_modes[ctx->mode]);
    cJSON_AddStringToObject(root,"kind",kind);
    cJSON_AddItemToObject(root,"data",data);
    char *encoded=cJSON_PrintUnformatted(root);
    /* qm_cli_printf has a 256-byte stack buffer and silently cuts JSON frames. */
    if (encoded) { printf("\r\nBLAB1 %s\r\n",encoded); fflush(stdout); cJSON_free(encoded); }
    xSemaphoreGive(s_print); cJSON_Delete(root);
}
static void status(const char *kind, const char *id, const char *result) {
    context_t ctx=context(); cJSON *d=cJSON_CreateObject();
    cJSON_AddStringToObject(d,"command_id",id?id:"");
    cJSON_AddStringToObject(d,"status",result);
    cJSON_AddNumberToObject(d,"queue_drops",__atomic_load_n(&s_drops,__ATOMIC_RELAXED));
    emit(&ctx,now_ms(),kind,d);
}
static void on_event(void *arg,qm_event_base_t base,int32_t kind,void *ptr,size_t bytes) {
    (void)arg;
    if (base!=QM_AGENT_EVENT_BASE || !ptr || bytes!=sizeof(qm_agent_event_notice_t)) return;
    const qm_agent_event_notice_t *n=ptr;
    portENTER_CRITICAL(&s_lock);
    if (kind==QM_AGENT_EVENT_AGENT_STATE) s_dialog=n->data.agent_state.state;
    if (s_busy && (kind==QM_AGENT_EVENT_TTS_PLAYBACK_STARTED ||
                   kind==QM_AGENT_EVENT_TTS_PLAYBACK_COMPLETE || kind==QM_AGENT_EVENT_TTS_PLAYBACK_FAILED)) {
        if (s_play_generation && s_play_generation!=n->generation) s_ambiguous=1;
        if (n->generation) s_play_generation=n->generation;
        if (kind==QM_AGENT_EVENT_TTS_PLAYBACK_STARTED) s_started=1;
        if (kind==QM_AGENT_EVENT_TTS_PLAYBACK_COMPLETE) s_complete=1;
        if (kind==QM_AGENT_EVENT_TTS_PLAYBACK_FAILED) s_failed=1;
    }
    context_t ctx=s_context;
    portEXIT_CRITICAL(&s_lock);
    if (kind==QM_AGENT_EVENT_CONNECTED) {
        /* record may precede Agent startup; refresh upload now that it is running. */
        (void)agent_app_set_resource_mode(ctx.mode==2?QM_TRUE:QM_FALSE);
    }
    if (kind!=QM_AGENT_EVENT_ASR && kind!=QM_AGENT_EVENT_TTS && kind!=QM_AGENT_EVENT_AGENT_TEXT) return;
    if (!n->data.text.final || !ctx.experiment[0] || (ctx.mode!=1 && ctx.mode!=2 && ctx.mode!=3)) return;
    event_t e={.context=ctx,.time=now_ms(),.kind=kind,.notice=*n};
    if (xQueueSend(s_events,&e,0)!=pdTRUE) __atomic_add_fetch(&s_drops,1,__ATOMIC_RELAXED);
}
static void event_worker(void *unused) {
    (void)unused; event_t e;
    while (1) {
        if (xQueueReceive(s_events,&e,pdMS_TO_TICKS(1000))!=pdTRUE) continue;
        context_t ctx=context(); if (ctx.epoch!=e.context.epoch) continue;
        size_t n=e.notice.data.text.text_length;
        if (n>=QM_AGENT_EVENT_TEXT_BYTES) n=QM_AGENT_EVENT_TEXT_BYTES-1;
        size_t valid=utf8_prefix(e.notice.data.text.text,n);
        char copy[QM_AGENT_EVENT_TEXT_BYTES]; memcpy(copy,e.notice.data.text.text,valid); copy[valid]=0;
        int truncated=e.notice.data.text.truncated || valid!=n;
        cJSON *d=cJSON_CreateObject();
        cJSON_AddStringToObject(d,"text",copy);
        cJSON_AddBoolToObject(d,"final",1); cJSON_AddBoolToObject(d,"truncated",truncated);
        cJSON_AddBoolToObject(d,"usable_for_confirmation",!truncated && valid>0);
        cJSON_AddBoolToObject(d,"confirmed",0);
        cJSON_AddStringToObject(d,"source",e.kind==QM_AGENT_EVENT_ASR?"user_reported":"agent_generated");
        cJSON_AddNumberToObject(d,"source_agent_instance_id",e.notice.agent_id);
        cJSON_AddNumberToObject(d,"source_request_id",e.notice.request_id);
        cJSON_AddNumberToObject(d,"source_generation",e.notice.generation);
        cJSON_AddNumberToObject(d,"finish_reason",e.notice.data.text.finish_reason);
        emit(&e.context,e.time,e.kind==QM_AGENT_EVENT_ASR?"asr.final":
             e.kind==QM_AGENT_EVENT_TTS?"tts.final":"agent.final",d);
    }
}
static void speech_worker(void *unused) {
    (void)unused; speech_t s;
    while (1) {
        xQueueReceive(s_speech,&s,portMAX_DELAY);
        context_t ctx=context();
        if (ctx.epoch!=s.context.epoch || s.cancellation!=__atomic_load_n(&s_cancel,__ATOMIC_RELAXED) || ctx.mode!=2 || now_ms()>=s.deadline) {
            status("speech.status",s.id,"cancelled_or_stale"); continue;
        }
        portENTER_CRITICAL(&s_lock);
        int blocked=s_dialog==QM_AGENT_DIALOG_STATE_THINKING || s_dialog==QM_AGENT_DIALOG_STATE_SPEAKING;
        if (!blocked) { s_busy=1; s_started=s_complete=s_failed=s_ambiguous=0; s_play_generation=0; }
        portEXIT_CRITICAL(&s_lock);
        if (blocked) { status("speech.status",s.id,"native_output_busy"); continue; }
        int ret=agent_app_set_resource_mode(QM_TRUE);
        if (ret==QM_EOK) ret=agent_app_user_corpus(s.text);
        if (ret==QM_EOK) {
            status("speech.status",s.id,"submitted");
            ret=agent_app_wait_tts_complete(15000);
        }
        portENTER_CRITICAL(&s_lock);
        int observed=s_started&&s_complete&&!s_failed&&!s_ambiguous;
        int failed=s_failed; s_busy=0;
        portEXIT_CRITICAL(&s_lock);
        (void)agent_app_set_resource_mode(context().mode==2?QM_TRUE:QM_FALSE);
        /* SDK wait can return OK after PLAYBACK_FAILED; never report completion from ret alone. */
        const char *outcome=s.cancellation!=__atomic_load_n(&s_cancel,__ATOMIC_RELAXED)?"cancelled":failed?"playback_failed":
            ret!=QM_EOK?"request_or_wait_failed":observed?"uncorrelated_playback_observed":"playback_unconfirmed";
        status("speech.status",s.id,outcome);
    }
}
static int hex_value(char c) {
    if (c>='0'&&c<='9') return c-'0';
    if (c>='a'&&c<='f') return c-'a'+10;
    return -1;
}
static void cli(char *out,int len,int argc,char **argv) {
    (void)out;(void)len;
    if (argc==2 && !strcmp(argv[1],"status")) { status("device.status",NULL,"ready"); return; }
    if (argc==3 && !strcmp(argv[1],"sync") && identifier(argv[2],32)) {
        context_t ctx=context(); cJSON *d=cJSON_CreateObject();cJSON_AddStringToObject(d,"nonce",argv[2]);
        emit(&ctx,now_ms(),"clock.sync",d);return;
    }
    if (argc==3 && !strcmp(argv[1],"cancel") && identifier(argv[2],32)) {
        __atomic_add_fetch(&s_cancel,1,__ATOMIC_RELAXED);
        (void)agent_app_abort_output();status("device.status",argv[2],"cancel_requested");return;
    }
    if (argc==3 && !strcmp(argv[1],"bind") && identifier(argv[2],ID_LIMIT)) {
        portENTER_CRITICAL(&s_lock);
        int busy=s_busy || s_dialog==QM_AGENT_DIALOG_STATE_THINKING || s_dialog==QM_AGENT_DIALOG_STATE_SPEAKING;
        if (!busy) { memset(&s_context,0,sizeof(s_context));
            s_context.epoch=__atomic_add_fetch(&s_cancel,1,__ATOMIC_RELAXED);
            memcpy(s_context.experiment,argv[2],strlen(argv[2])); }
        portEXIT_CRITICAL(&s_lock);
        if (!busy) (void)agent_app_set_resource_mode(QM_FALSE);
        status("device.status",NULL,busy?"busy":"bound");return;
    }
    if (argc==4 && !strcmp(argv[1],"mode") && identifier(argv[2],32)) {
        int selected=-1; for (int i=0;i<6;i++) if (!strcmp(argv[3],s_modes[i])) selected=i;
        portENTER_CRITICAL(&s_lock);
        int previous=s_context.mode;
        int rejected=selected<0 || !s_context.experiment[0] || s_busy;
        if (!rejected) { s_context.mode=selected;__atomic_add_fetch(&s_cancel,1,__ATOMIC_RELAXED); }
        portEXIT_CRITICAL(&s_lock);
        if (rejected) { status("device.status",argv[2],"mode_rejected");return; }
        if (agent_app_set_resource_mode(selected==2?QM_TRUE:QM_FALSE)!=QM_EOK) {
            portENTER_CRITICAL(&s_lock);s_context.mode=previous;portEXIT_CRITICAL(&s_lock);
            status("device.status",argv[2],"resource_mode_unavailable");return;
        }
        status("device.status",argv[2],"mode_set");return;
    }
    if (argc==5 && !strcmp(argv[1],"speak") && identifier(argv[2],32)) {
        static char ids[16][33],texts[16][TEXT_LIMIT+1];static unsigned next;
        speech_t s={.context=context(),.cancellation=__atomic_load_n(&s_cancel,__ATOMIC_RELAXED)};
        char *end; unsigned long ttl=strtoul(argv[3],&end,10);
        if (!argv[3][0] || *end || ttl<1 || ttl>60000) goto invalid;
        s.deadline=now_ms()+ttl;
        size_t n=strlen(argv[4]);
        if (!n || n%2 || n>TEXT_LIMIT*2 || s.context.mode!=2 || !s.context.experiment[0]) goto invalid;
        for (size_t i=0;i<n;i+=2) {
            int a=hex_value(argv[4][i]),b=hex_value(argv[4][i+1]);
            if (a<0||b<0||!(a*16+b)) goto invalid;
            s.text[i/2]=(char)(a*16+b);
        }
        if (utf8_prefix(s.text,n/2)!=n/2) goto invalid;
        strcpy(s.id,argv[2]);
        for (int i=0;i<16;i++) if (!strcmp(ids[i],s.id)) {
            status("speech.status",s.id,strcmp(texts[i],s.text)?"id_conflict":"duplicate_not_replayed");return;
        }
        if (xQueueSend(s_speech,&s,0)!=pdTRUE) { status("speech.status",s.id,"queue_full");return; }
        strcpy(ids[next%16],s.id);strcpy(texts[next%16],s.text);next++;
        status("speech.status",s.id,"queued");return;
    }
invalid:
    status("device.status",NULL,"invalid_command");
}
static const struct qm_cli_command s_cli={"lab","Private lab events; see b/lab/README.md",cli};
int b_lab_init(void) {
    if (s_events) return -QM_EINIT;
    snprintf(s_boot,sizeof(s_boot),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
    s_print=xSemaphoreCreateMutex(); s_events=xQueueCreate(8,sizeof(event_t));s_speech=xQueueCreate(2,sizeof(speech_t));
    TaskHandle_t events=NULL,speech=NULL;
    int ret=-QM_ENOMEM;
    if (!s_print||!s_events||!s_speech) goto cleanup;
    ret=qm_event_default_create();if (ret!=QM_EOK && ret!=-QM_EINIT) goto cleanup;
    ret=-QM_ENOMEM;
    if (xTaskCreate(event_worker,"b_lab_events",4096,NULL,3,&events)!=pdPASS) goto cleanup;
    /* HTTP/TLS work uses an internal-RAM stack, never the event callback or B's PSRAM state task. */
    if (xTaskCreate(speech_worker,"b_lab_speech",8192,NULL,3,&speech)!=pdPASS) goto cleanup;
    ret=qm_cli_register_command(&s_cli);
    if (ret!=QM_EOK) goto cleanup;
    ret=qm_event_handler_register(QM_AGENT_EVENT_BASE,QM_EVENT_ANY_ID,on_event,NULL);
    if (ret==QM_EOK) return ret;
    (void)qm_cli_unregister_command(&s_cli);
cleanup:
    if (events) vTaskDelete(events);
    if (speech) vTaskDelete(speech);
    if (s_events) vQueueDelete(s_events);
    if (s_speech) vQueueDelete(s_speech);
    if (s_print) vSemaphoreDelete(s_print);
    s_events=s_speech=NULL;s_print=NULL;
    return ret;
}
