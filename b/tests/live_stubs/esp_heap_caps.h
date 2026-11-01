#include <stddef.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define MALLOC_CAP_INTERNAL 4
void *heap_caps_malloc(size_t size,int caps);
void heap_caps_free(void *ptr);
size_t heap_caps_get_free_size(int caps);
