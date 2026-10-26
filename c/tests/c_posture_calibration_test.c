#include "c_posture_calibration.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
static c_posture_geometry_t geom(float a,float s) {
    c_posture_geometry_t g={true,a,s}; return g;
}
static c_posture_state_t observe(c_posture_calibration_t *c,float a) {
    return c_posture_calibration_observe(c,geom(a,.5f));
}
static void learn(c_posture_calibration_t *c,float a) {
    c_posture_calibration_start(c);
    for (unsigned i=0;i<C_CAL_SAMPLE_COUNT;i++) { CHECK(observe(c,a)==C_POSTURE_UNKNOWN); }
    CHECK(c->state==C_CAL_READY);
}
int main(void) {
    c_posture_landmarks_t p={240,320,1,.9f,120,80,180,160,60,160};
    c_posture_geometry_t g;
    CHECK(c_posture_geometry_make(&p,&g));
    CHECK(g.valid && fabsf(g.angle_deg)<.01f && fabsf(g.scale-.5f)<.01f);
    p.left_y=176; p.right_y=144;
    CHECK(c_posture_geometry_make(&p,&g));
    CHECK(fabsf(g.angle_deg-14.9314f)<.02f);
    float original_angle=g.angle_deg,original_scale=g.scale;
    p.nose_x+=10;p.left_x+=10;p.right_x+=10;
    CHECK(c_posture_geometry_make(&p,&g)); CHECK(fabsf(g.angle_deg-original_angle)<.01f);
    p.width*=2;p.height*=2;p.nose_x*=2;p.nose_y*=2;p.left_x*=2;p.left_y*=2;p.right_x*=2;p.right_y*=2;
    CHECK(c_posture_geometry_make(&p,&g));
    CHECK(fabsf(g.angle_deg-original_angle)<.01f && fabsf(g.scale-original_scale)<.01f);
    p.people=2; CHECK(!c_posture_geometry_make(&p,&g));
    p.people=1;p.score=.4f; CHECK(!c_posture_geometry_make(&p,&g));
    p.score=.9f;p.left_x=0; CHECK(!c_posture_geometry_make(&p,&g));

    c_posture_calibration_t c; c_posture_calibration_init(&c);
    CHECK(observe(&c,0)==C_POSTURE_UNKNOWN && c.state==C_CAL_IDLE);
    learn(&c,15); CHECK(observe(&c,16)==C_POSTURE_NEUTRAL);
    CHECK(observe(&c,35)==C_POSTURE_DEVIATION);
    CHECK(observe(&c,24)==C_POSTURE_DEVIATION); /* Inside hysteresis band. */
    CHECK(observe(&c,20)==C_POSTURE_NEUTRAL);
    CHECK(observe(&c,-5)==C_POSTURE_DEVIATION); /* Opposite direction. */
    CHECK(c_posture_calibration_observe(&c,(c_posture_geometry_t){0})==C_POSTURE_UNKNOWN);
    CHECK(observe(&c,15)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_calibration_observe(&c,geom(15,1.0f))==C_POSTURE_UNKNOWN);
    CHECK(observe(&c,15)==C_POSTURE_NEUTRAL);

    c_posture_calibration_start(&c);
    for (unsigned i=0;i<C_CAL_SAMPLE_COUNT;i++) { (void)observe(&c,i%2 ? 12.f : -12.f); }
    CHECK(c.state==C_CAL_REJECTED && observe(&c,0)==C_POSTURE_UNKNOWN);
    c_posture_calibration_start(&c);
    for (unsigned i=0;i<3;i++) { (void)observe(&c,0); }
    (void)c_posture_calibration_observe(&c,(c_posture_geometry_t){0}); CHECK(c.count==0);
    for (unsigned i=0;i<C_CAL_SAMPLE_COUNT;i++) { (void)observe(&c,0); }
    CHECK(c.state==C_CAL_READY);
    c_posture_calibration_start(&c);
    for (unsigned i=0;i<C_CAL_SAMPLE_COUNT;i++) { (void)observe(&c,35); }
    CHECK(c.state==C_CAL_REJECTED); /* Excessive reference roll must be refused. */
    c_posture_calibration_start(&c);
    for (unsigned i=0;i<C_CAL_SAMPLE_COUNT;i++) { (void)observe(&c,i==9 ? 15.f : 0.f); }
    CHECK(c.state==C_CAL_READY && fabsf(c.baseline_deg)<.01f);
    CHECK(observe(&c,3)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_calibration_observe(&c,geom(NAN,.5f))==C_POSTURE_UNKNOWN);

    learn(&c,0);
    c_posture_filter_t f; c_posture_filter_init(&f);
    CHECK(c_posture_filter_update(&f,observe(&c,0),1000)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,observe(&c,20),3000)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,observe(&c,0),5000)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,observe(&c,20),7000)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,observe(&c,20),9000)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,observe(&c,20),11000)==C_POSTURE_DEVIATION);
    CHECK(c_posture_filter_update(&f,observe(&c,0),13000)==C_POSTURE_DEVIATION);
    CHECK(c_posture_filter_update(&f,observe(&c,0),15000)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,C_POSTURE_UNKNOWN,17000)==C_POSTURE_UNKNOWN);
    puts("PASS: geometry, calibration quality, camera offset, hysteresis and real-cadence debounce");
    return 0;
}
