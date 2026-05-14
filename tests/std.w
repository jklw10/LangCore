
bool : value[bool] = (byte[0:1]):{
    value = byte;
    // Control Flow (Null-Denotation / Prefix)
    .@expr(2, if, cond, t_body) : out = (cond[bool], t_body) : {
        @asm(beq, cond, zero, skip_body);
        t_body;
        @asm(label, skip_body)
    };
    .@expr(8, a, &&, b) : out[bool] = (a[bool], b) : {
        @asm(and_, out, a, b);
    };

    .@expr(7, a, ||, b) : out[bool] = (a[bool], b) : {
        @asm(or_, out, a, b);
    };

    .@expr(11, !, a) : out[bool] = (a[bool]) : {
        @asm(xori, out, a, 1);
    };
};
@using(bool);
//Math Operators (Left-Denotation / Infix)
int : value[int] = (bytes[0:4]):{
    value = bytes;
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
    
    _udiv_loop : q[int], r[int] = (n[int], d[int], q_in[int], r_in[int], 32) : {
        q = q_in;
        r = r_in;
    };

    // Recursive Step: branchless evaluation
    _udiv_loop : q[int], r[int] = (n[int], d[int], q_in[int], r_in[int], j[int]) : {
        // i = 31 - j  (We iterate downwards from the MSB)
        @asm(addi, t0, zero, 31);
        @asm(sub, i, t0, j);

        // r = (r << 1) | ((n >> i) & 1)
        @asm(slli, t0, r_in, 1);
        @asm(srl, t1, n, i);
        @asm(andi, t1, t1, 1);
        @asm(or_, next_r, t0, t1);

        // Branchless Conditional: is_ge = (next_r >= d) ? 1 : 0
        @asm(sltu, is_less, next_r, d); // is_less = next_r < d
        @asm(xori, is_ge, is_less, 1);  // Invert boolean

        // Branchless Subtract: mask will be 0xFFFFFFFF if is_ge is 1, else 0x00000000
        @asm(sub, mask, zero, is_ge);   
        @asm(and_, sub_val, d, mask);    // sub_val = is_ge ? d : 0
        @asm(sub, next_r_final, next_r, sub_val); 

        // Branchless Quotient Bit Set
        @asm(sll, bit, is_ge, i);       
        @asm(or_, next_q_final, q_in, bit); 

        // Tail Recurse to next bit
        q, r = _udiv_loop(n, d, next_q_final, next_r_final, j + 1);
    };
    
    div_rem : q[int], r[int] = (n[int], d[int]) : {
        q, r = _udiv_loop(n, d, 0, 0, 0);
    };
    .@expr(10, a, /, b) : out[int] = (a[int], b) : {
        out, _r_trash = div_rem(a, b);
    };
    
    // Software Modulo/Remainder Operator ( a % b )
    .@expr(10, a, %, b) : out[int] = (a[int], b) : {
        _q_trash, out = div_rem(a, b);
    };
    
    .rand : value[int] = ():{
        value = 4; //decided by fair dice
    };
};
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
