#include "lib/stdio.h"
#include "lib/stdlib.h"
#include "lib/bool.h"
int add(int a, int b)
{
    return a + b;
}

int main()
{
    int x = 5;
    int y = 10;
    int result = add(x, y);
    print_string("The result of 10 + 5 is: ");
    printi(result);
    int *ptr = (int *)malloc(sizeof(int));
    if (ptr)
    {
        *ptr = 42;
        print_string("Dynamically allocated integer value (42): ");
        printi(*ptr);
        free(ptr);
    }
    else
    {
        print_string("Memory allocation failed");
    }
    return 0;
}