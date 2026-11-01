#ifndef SPI_TEST_QM_H
#define SPI_TEST_QM_H
#define QM_EOK 0
void spi_test_log(const char *tag,const char *format,...);
#define QM_LOGI spi_test_log
#define QM_LOGW spi_test_log
#endif
