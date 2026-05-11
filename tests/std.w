
bool : value[bool] = (byte[0:1]):{
    .value = byte;
    // Control Flow (Null-Denotation / Prefix)
    .@expr(2, if, cond, t_body) : out = (cond[bool], t_body) : {
        @asm(beq, cond, zero, skip_body);
        t_body;
        @asm(label, skip_body)
    };
    .@expr(8, a, &&, b) : out[bool] = (a[bool], b) : {
        @asm(and, out, a, b);
    };

    .@expr(7, a, ||, b) : out[bool] = (a[bool], b) : {
        @asm(or, out, a, b);
    };

    .@expr(11, !, a) : out[bool] = (a[bool]) : {
        @asm(xori, out, a, 1);
    };
};

//Math Operators (Left-Denotation / Infix)
int : value[int] = (bytes[0:4]):{
    .value = bytes;
    .max = int(0x7fff);
    
    // 1. Math Operators
    .@expr(10, a, +, b) : out[int] = (a[int], b) : {
        @asm(add, out, a, b);
    };
    .@expr(10, a, -, b) : out[int] = (a[int], b) : {
        @asm(sub, out, a, b);
    };
    .@expr(9, a, <, b) : out[bool] = (a[int], b) : {
        @asm(slt, out, a, b);
    };
    .@expr(9, a, >, b) : out[bool] = (a[int], b) : {
        @asm(slt, out, b, a);
    };
    .@expr(9, a, <=, b) : out[bool] = (a[int], b) : {
        @asm(slt, out, b, a);
        @asm(xori, out, out, 1); // !(b < a) => a <= b
    };
    .@expr(9, a, >=, b) : out[bool] = (a[int], b) : {
        @asm(slt, out, a, b);
        @asm(xori, out, out, 1); // !(a < b) => a >= b
    };
    .@expr(9, a, ==, b) : out[bool] = (a[int], b) : {
        @asm(sub, out, a, b);
        @asm(sltiu, out, out, 1);
    };
    .@expr(9, a, !=, b) : out[bool] = (a[int], b) : {
        @asm(sub, out, a, b);
        @asm(sltu, out, zero, out); // if (a-b) != 0, 0 < unsigned(a-b) is true
    };

    .rand : value[int] = ():{
        value = 4; //decided by fair dice
    };
};
//does this need a shorthand?:
sys : value[int] = (bytes[0:0]): {
    .read_stdin : bytes_read[int] = (dest_ptr[int], max_len[int]) : {
        @asm(addi, x17, zero, 3); // Syscall 3: Read
        @asm(add, x11, zero, dest_ptr);
        @asm(add, x12, zero, max_len);
        @asm(ecall);
        @asm(add, bytes_read, zero, x10); // Returns bytes read in a0
    };

    .read : [ptr] = (ptr[int], len[int]) : {
        @asm(addi, x17, zero, 3); // Syscall 3: read stdout
        @asm(add, x11, zero, ptr);
        @asm(add, x12, zero, len);
        @asm(ecall);
    };
    .write : _ = (ptr[int], len[int]) : {
        @asm(addi, x17, zero, 2); // Syscall 2: write stdout
        @asm(add, x11, zero, ptr);
        @asm(add, x12, zero, len);
        @asm(ecall);
    };
    .print_int : _ = (val[int]) : {
        @asm(addi, x17, zero, 1); // Syscall 1: Print Int
        @asm(add, x10, zero, val);
        @asm(ecall);
    };
    .@expr(2, assert, cond) : _ = (cond[bool]) : {
        @asm(bne, cond, zero, assert_ok);
        // If condition is 0 (false), crash immediately
        @asm(addi, x17, zero, 0); // Syscall 0: HALT
        @asm(ecall);
        @asm(label, assert_ok);
    };
}
