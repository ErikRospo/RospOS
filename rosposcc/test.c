int fib(int n) {
    if (n <= 1) {
        return n;
    }
    return fib(n - 1) + fib(n - 2);
}

int main() {
    char h = 72; // ASCII 'H'
    char *out = (char *)0x10000000; // Filthy hardcoded tty address (virtual hardware)
    *out = h; // Print 'H'
    int result = fib(8); // Calculate fib(8) = 21
    result*=2; // Multiply by 2 to get 42
    return result; // Exit code 42
}