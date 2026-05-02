// =========================================================================
// W Kernel Architecture - Capabilities Test
// =========================================================================
// The compiler has zero built-in keywords. We bootstrap the language 
// natively using the @expr macro engine and raw @asm intrinsics.

// -------------------------------------------------------------
// 1. Math Operators (Left-Denotation / Infix)
// -------------------------------------------------------------
@expr(10, a, +, b) : out = (a, b) : {
    @asm(add, out, a, b);
};

@expr(10, a, -, b) : out = (a, b) : {
    @asm(sub, out, a, b);
};

// -------------------------------------------------------------
// 2. Logic Operators
// -------------------------------------------------------------
@expr(9, a, <, b) : out = (a, b) : {
    @asm(slt, out, a, b);
};

@expr(9, a, ==, b) : out = (a, b) : {
    @asm(sub, out, a, b);
    @asm(sltiu, out, out, 1);
};

// -------------------------------------------------------------
// 3. Control Flow (Null-Denotation / Prefix)
// -------------------------------------------------------------
// The "if" statement is just syntactic sugar for a temporal pipeline
// constrained to run at most exactly once.
@expr(2, if, cond, t_body) : out = (cond, t_body) : {
    _run = cond;
    (_run) : {
        t_body;
        _run = 0; // Mutating the loop condition breaks us out immediately
    };
};


// =========================================================================
// Main Execution Payload
// =========================================================================

i = 0;
sum = 0;

// Zero-Keyword Branching: The pipeline natively acts as a temporal `while` loop
(i < 10) : {
    sum = sum + i;
    
    // Test the newly defined "if" statement block!
    // 0 + 1 + 2 + 3 + 4 + 5 = 15
    if (sum == 15) {
        
        // 65000 (0xFDE8) is the emulator's memory-mapped visual display flag.
        ptr = 65000;
        
        // Native pointer dereferencing assignment
        [ptr] = sum;
        
    };

    i = i + 1;
};


foo : res = (1, 2) : { res = 10 };
foo : res = (x, 2) : { res = x + 10 };
foo : res = (x, y) : { res = 99 };

[65000] = foo(1, 2); // Will be 10
[65000] = foo(2, 2); // Will be 20
[65000] = foo(5, 5); // Will be 99