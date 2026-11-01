#ifndef SPI_TEST_SPEC_H
#define SPI_TEST_SPEC_H
#include <stdint.h>
typedef struct { uint8_t siid; uint16_t piid; int value; int invalid_type; } qm_spec_property_t;
typedef struct { int count; qm_spec_property_t *properties[6]; } qm_spec_property_operation_t;
qm_spec_property_t *qm_spec_property_creat(void);
int qm_spec_property_delete(qm_spec_property_t *p);
int qm_spec_property_pack_xiid(qm_spec_property_t *p,uint8_t siid,uint16_t piid);
int qm_spec_property_pack_number(qm_spec_property_t *p,int value);
int qm_spec_property_unpack_number(qm_spec_property_t *p,int *value);
qm_spec_property_operation_t *qm_spec_property_operation_creat(void);
int qm_spec_property_operation_delete(qm_spec_property_operation_t *op);
int qm_spec_property_add(qm_spec_property_operation_t *op,qm_spec_property_t *p);
#endif
