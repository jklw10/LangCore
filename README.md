The main idea is to have a language that you have to define just about everything about the language.
original idea was a language you can define as you write it, so [yacc](https://en.wikipedia.org/wiki/Yacc) with extra steps

Language documentation sanity is: surface level verified gemini output.

a simple hello world: :^)
```py
write : _ = (ptr, len) : {
        @asm(addi, x17, zero, 2); // Syscall 2: write stdout
        @asm(add, x11, zero, ptr);
        @asm(add, x12, zero, len);
        @asm(ecall);
};
ptr = 1000; 
@expr(10, a, +, b) : out = (a, b) : {
        @asm(add, out, a, b);
};
[ptr]     = 0x6C6C6548; // "Hell"
[ptr + 4] = 0x6F57206F; // "o Wo"
[ptr + 8] = 0x21646C72; // "rld!"

write(ptr, 12);
```
