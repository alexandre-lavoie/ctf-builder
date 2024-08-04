#include <stdio.h>

#ifdef FLAG
#define STRINGIZE(x) #x
#define STRINGIZE_VALUE_OF(x) STRINGIZE(x)
#define FLAG_STR STRINGIZE_VALUE_OF(FLAG)
#else
#define FLAG_STR "FLAG"
#endif

int main() {
    printf("Flag: %s\n", FLAG_STR);
}
