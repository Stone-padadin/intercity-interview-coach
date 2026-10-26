#include "c_posture_calibration.h"
#include <math.h>

static bool inside(int x,int y,int w,int h) {
    return x>2 && y>2 && x<w-3 && y<h-3;
}
bool c_posture_geometry_make(const c_posture_landmarks_t *p,c_posture_geometry_t *o)
{
    if (!o) { return false; }
    *o=(c_posture_geometry_t){0};
    if (!p || p->width<20 || p->height<20 || p->people!=1 ||
        !isfinite(p->score) || p->score<.55f ||
        !inside(p->nose_x,p->nose_y,p->width,p->height) ||
        !inside(p->left_x,p->left_y,p->width,p->height) ||
        !inside(p->right_x,p->right_y,p->width,p->height)) { return false; }
    float dx=(float)p->left_x-p->right_x,dy=(float)p->left_y-p->right_y;
    if (dx<0) { dx=-dx; dy=-dy; }
    float span=hypotf(dx,dy);
    if (dx<1 || span<30 || span<.2f*p->width) { return false; }
    o->angle_deg=atan2f(dy,dx)*57.2957795f;
    o->scale=span/p->width; o->valid=true;
    return true;
}

static float median(const float *data) {
    float values[C_CAL_SAMPLE_COUNT];
    for (unsigned i=0;i<C_CAL_SAMPLE_COUNT;i++) {
        values[i]=data[i];
        for (unsigned j=i;j>0 && values[j]<values[j-1];j--) {
            float temp=values[j];values[j]=values[j-1];values[j-1]=temp;
        }
    }
    return (values[C_CAL_SAMPLE_COUNT/2-1]+values[C_CAL_SAMPLE_COUNT/2])*.5f;
}

static void finish(c_posture_calibration_t *c) {
    float deviations[C_CAL_SAMPLE_COUNT];
    c->baseline_deg=median(c->angles); c->baseline_scale=median(c->scales);
    float minimum=c->angles[0],maximum=c->angles[0];
    bool scale_ok=true;
    for (unsigned i=0;i<C_CAL_SAMPLE_COUNT;i++) {
        deviations[i]=fabsf(c->angles[i]-c->baseline_deg);
        minimum=fminf(minimum,c->angles[i]); maximum=fmaxf(maximum,c->angles[i]);
        float ratio=c->scales[i]/c->baseline_scale;
        if (ratio<.8f || ratio>1.2f) { scale_ok=false; }
    }
    c->noise_deg=median(deviations);
    if (maximum-minimum>18 || c->noise_deg>3 || fabsf(c->baseline_deg)>30 || !scale_ok) {
        c->state=C_CAL_REJECTED; return;
    }
    c->enter_deg=fmaxf(12,4*c->noise_deg+3); c->exit_deg=c->enter_deg*.65f;
    c->state=C_CAL_READY;
}

void c_posture_calibration_init(c_posture_calibration_t *c) { *c=(c_posture_calibration_t){0}; }
void c_posture_calibration_start(c_posture_calibration_t *c) { c_posture_calibration_init(c); c->state=C_CAL_COLLECTING; }
c_posture_state_t c_posture_calibration_observe(c_posture_calibration_t *c,c_posture_geometry_t g)
{
    c->delta_deg=0;
    if (!g.valid || !isfinite(g.angle_deg) || !isfinite(g.scale) || g.scale<=0) {
        if (c->state==C_CAL_COLLECTING) { c->count=0; }
        c->deviation=false;
        return C_POSTURE_UNKNOWN;
    }
    if (c->state==C_CAL_COLLECTING) {
        c->angles[c->count]=g.angle_deg; c->scales[c->count]=g.scale; c->count++;
        if (c->count==C_CAL_SAMPLE_COUNT) { finish(c); }
        return C_POSTURE_UNKNOWN; /* Validation starts on a separate next sample. */
    }
    if (c->state!=C_CAL_READY) { return C_POSTURE_UNKNOWN; }
    float ratio=g.scale/c->baseline_scale;
    if (ratio<.65f || ratio>1.5f) { c->deviation=false; return C_POSTURE_UNKNOWN; }
    c->delta_deg=g.angle_deg-c->baseline_deg;
    if (fabsf(c->delta_deg)>=c->enter_deg) { c->deviation=true; }
    else if (fabsf(c->delta_deg)<=c->exit_deg) { c->deviation=false; }
    return c->deviation ? C_POSTURE_DEVIATION : C_POSTURE_NEUTRAL;
}
