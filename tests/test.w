// 1. Math Operators (Left-Denotation / Infix)
bool:value = (byte[:1]):{
    .value = byte;
    2. Logic Operators
    
    3. Control Flow (Null-Denotation / Prefix)
    .@expr(2, if, cond, t_body) : out = (cond[bool], t_body) : {
        runner = (cond == 1) : {
            t_body;
        };
        runner(cond);
    };
};

int:value = (bytes[:4]):{
    .value = bytes;
    .max = int(0x7fff);
    .@expr(10, a, +, b) : out[int] = (a[int], b) : {
        @asm(add, out, a, b);
    };

    .@expr(10, a, -, b) : out[int] = (a[int], b) : {
        @asm(sub, out, a, b);
    };
    .@expr(9, a, <, b) : out[bool] = (a[int], b) : {
        @asm(slt, out, a, b);
    };

    .@expr(9, a, ==, b) : out[bool] = (a[int], b) : {
        @asm(sub, out, a, b);
        @asm(sltiu, out, out, 1);
    };
    .rand : value = ():{
        value = 4; //decided by fair dice
    }
};


i[int] = 0;
sum[int] = 0;

// Temporal loop pipeline
(i < 10) : {
    sum = sum + i;
    
    // (sum == 15) successfully yields a [bool], triggering the 'if' macro!
    if (sum == 15) {
        ptr = 65000;
        [ptr] = sum;
    };

    i = i + 1;
};

// Function Definitions dynamically returning an [int] type
//atm this is just nameless value inserts idk which i like more, 
//implicit type check with x[int]==0 vs x[bool]==0 would be kind of interesting though.
//i suppose you could just go with 0[int].
//on one hand if i'm defining the value i know what it is so i could just define x in the ctx, 
//but that's multiple sources of truth on some level
foo : res[int] = (1, 2) : { res = 10 };
foo : res[int] = (x, 2) : { res = x + 10 };
foo : res[int] = (x, y) : { res = 99 };

[65000] = foo(1, 2); // Will be 10
[65000] = foo(2, 2); // Will be 20
[65000] = foo(5, 5); // Will be 99