
bool : value[bool] = (byte[0:1]):{
    .value = byte;
    // Control Flow (Null-Denotation / Prefix)
    .@expr(2, if, cond, t_body) : out = (cond[bool], t_body) : {
        @asm(beq, cond, zero, skip_body);
        t_body;
        @asm(label, skip_body)
    }
};

//Math Operators (Left-Denotation / Infix)
int : value[int] = (bytes[0:4]):{
    .value = bytes;
    .@expr(10, a, +, b) : out[int] = (a[int], b) : {
        @asm(add, out, a, b);
    };
    .@expr(10, a, -, b) : out[int] = (a[int], b) : {
        @asm(sub, out, a, b);
    };
    //2. Logic Operators
    .@expr(9, a, <, b) : out[bool] = (a[int], b) : {
        @asm(slt, out, a, b);
    };
    .@expr(9, a, ==, b) : out[bool] = (a[int], b) : {
        @asm(sub, out, a, b);
        @asm(sltiu, out, out, 1);
    };
};
@using(bool);
@using(int);

loop : sum[int], [ptr] = (0, i[int], sum[int], ptr) : {
    sum = sum;
} 
loop : sum[int], [ptr] = (1, i[int], sum[int], ptr) : {
    sum = sum + i;
    
    // (sum == 15) a [bool], triggering the 'if' macro!
    if (sum == 15) {
        [ptr] = sum;
    };
    
    sum, [ptr] = loop(i<10, i + 1, sum, ptr);
};

i[int] = 0;
sum[int] = 0;
ptr = 65000;
sum, [ptr] = loop(1, i, sum, ptr)