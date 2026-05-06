
bool : value[bool] = (byte[0:1]):{
    .value = byte;
    // Control Flow (Null-Denotation / Prefix)
    .@expr(2, if, cond, t_body) : out = (cond[bool], t_body) : {
        runner: _  = (1) : {
            t_body;
        };
        runner: _  = (cond) : {};
        runner(cond);
    };
};

//Math Operators (Left-Denotation / Infix)
int : value[int] = (bytes[0:4]):{
    .value = bytes;
    .max = int(0x7fff);
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
    .@expr(9, a, >=, b) : out[bool] = (a[int], b) : {
        @asm(slt, out, b, a);
    };
    .@expr(9, a, ==, b) : out[bool] = (a[int], b) : {
        @asm(sub, out, a, b);
        @asm(sltiu, out, out, 1);
    };
    .rand : value[int] = ():{
        value = 4; //decided by fair dice
    }
};
@using(bool);
@using(int);

// Temporal loop pipeline
loop : sum[int], [ptr] = (0, i[int], sum[int], ptr) : {
    sum = sum;
} 
loop : sum[int], [ptr] = (1, i[int], sum[int], ptr) : {
    sum = sum + i;
    
    // (sum == 15) a [bool], triggering the 'if' macro!
    if (sum == 15) {
        [ptr] = sum;
    };

    loop(i<10, i + 1, sum, ptr);
};

i[int] = 0;
sum[int] = 0;
ptr = 65000;
sum, [ptr] = loop(1, i, sum, ptr)


// Function Definitions dynamically returning an [int] type 
// i need to look into defining 2[int] or int(2) as input types instead of assuming type here:

foo : res[int] = (1, 2) : { res = 10 };
foo : res[int] = (x, 2) : { res = x + 10 };
foo : res[int] = (x, y) : { res = 99 };

[65000] = foo(1, 2); // Will be 10
[65000] = foo(2, 2); // Will be 20
[65000] = foo(5, 5); // Will be 99