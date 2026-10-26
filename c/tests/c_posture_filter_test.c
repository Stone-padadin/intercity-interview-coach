#include "c_posture_filter.h"
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
int main(void) {
    c_posture_filter_t f;
    c_posture_filter_init(&f);
    CHECK(c_posture_filter_read(&f,0)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_NEUTRAL,100)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,200)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,C_POSTURE_NEUTRAL,300)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,1000)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,2000)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,2500)==C_POSTURE_DEVIATION);
    CHECK(c_posture_filter_update(&f,C_POSTURE_NEUTRAL,2600)==C_POSTURE_DEVIATION);
    CHECK(c_posture_filter_update(&f,C_POSTURE_NEUTRAL,3100)==C_POSTURE_NEUTRAL);
    /* A ~2s inference and the next ~2s inference must not cause validity flicker. */
    CHECK(c_posture_filter_read(&f,7099)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_read(&f,9101)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,10000)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_UNKNOWN,10100)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,10200)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,11200)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,11700)==C_POSTURE_DEVIATION);
    CHECK(c_posture_filter_update(&f,C_POSTURE_UNKNOWN,11800)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_NEUTRAL,11900)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,C_POSTURE_NEUTRAL,11800)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_read(&f,11800)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_NEUTRAL,12000)==C_POSTURE_NEUTRAL);
    CHECK(c_posture_filter_update(&f,(c_posture_state_t)99,12100)==C_POSTURE_UNKNOWN);
    c_posture_filter_init(&f);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,0)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,1000)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,1000)==C_POSTURE_UNKNOWN);
    CHECK(c_posture_filter_update(&f,C_POSTURE_DEVIATION,1500)==C_POSTURE_DEVIATION);
    puts("PASS: posture debounce, recovery, unknown, stale, invalid and timestamp cases");
    return 0;
}
