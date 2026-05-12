If there's a decision to be made ask, if there's a discrepancy between docs and code or discussion, point it out.
I'm not using any coding tools, so just output the functions that were changed.

negative space programming, aka asserts everywhere:
no trivial asserts like assert true or assert out on a value you just assigned.
assert on values that aren't immediately obvious from the nearby code context what they should be.

during debugging:
    if i get assembly output:
        to collect all the logical mistakes happening in the assembly. point out the line numbers in assembly and the approximate locale in the language that most likely defines. i    will then prune the context to just those pieces so give yourself enough context. after you're done with that, i will prune the binary out of this context and give you the    compiler that produced it, and your job is to make asserts that catch the data that caused this error.
    
    if i hit an assert:
        we'll try to fix the errors.

current task:

strings, but declaration only allowed at the "top" (root) of type/namespace definitions, a file is a namespace/type
this is a namespace/type to store some bindings.
a middle ground between no strings, and yes strings.

Bindings : self[Bindings] = (_[0:0]) : {
 .transform = "u_transform";
 .color     = "u_color";
 .fmt_int   = "Value: %d\n";
 .loop : sum = (i) : {
    // ERROR: Cannot allocate static .rodata inside a dynamic stack scope.
    loc = glGetUniformLocation(shader, "u_transform"); 
    
    // VALID: Passing the pointer to the static memory.
    loc = glGetUniformLocation(shader, .transform);
    
    printf(Bindings.fmt_int, loc);
 }
}

std.w:


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


tokenizer.w:

@import(tests/std.w);

@using(bool);
@using(int);
@using(sys);

SOURCE_PTR = 1000; //we live in hope
MAX_LEN = 4096;

// Function to read a single byte (Since we don't have [byte] lens yet)
read_byte : val[int] = (ptr[int]) : {
    // raw assembly to load byte unsigned (lbu) into 'val'
    // Corrected positional arguments: (inst, rd, rs1, offset)
    @asm(lbu, val, ptr, 0); 
};

// --- Lexer State Machine ---
// loop signature: (is_done, current_ptr, max_ptr)
parse_loop : _ = (1, ptr[int], max_ptr[int]) : {
    // Done!
};

parse_loop : _ = (0, ptr[int], max_ptr[int]) : {
    char = read_byte(ptr);
    
    // Check if whitespace (space = 32, \n = 10)
    is_space = char == 32;
    is_newline = char == 10;
    
    // Negative Space constraint: we assert char is within ASCII bounds
    assert(char < 128);

    if (is_space) {
        // Skip
    };
    
    if (is_newline) {
        // Increment line number (to be implemented)
    };

    // TODO: Implement digit checks (char >= 48 && char <= 57)
    // TODO: Implement identifier checks

    // Recurse to next byte
    next_ptr = ptr + 1;
    is_done = next_ptr == max_ptr;
    
    _ = parse_loop(is_done, next_ptr, max_ptr);
};


// --- Main Execution ---
bytes_read = sys.read_stdin(SOURCE_PTR, MAX_LEN);

// Assert we actually read a file
assert(bytes_read > 0);

// Start State Machine
end_ptr = SOURCE_PTR + bytes_read;
_ = parse_loop(0, SOURCE_PTR, end_ptr);


test.w:

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

// loop i >= 10 branch
loop : sum[int], [ptr] = (0, i[int], sum[int], ptr) : {
    sum = sum;
} 
// loop i < 10 branch
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

// Function Definitions dynamically returning an [int] type 
// i need to look into forcing 2[int] or int(2) as input types instead of assuming type here:

foo : res[int] = (1, 2) : { res = 10 };
foo : res[int] = (x, 2) : { res = x + 10 };
foo : res[int] = (x, y) : { res = 99 };

[65000] = foo(1, 2); // Will be 10
[65000] = foo(2, 2); // Will be 20
[65000] = foo(5, 5); // Will be 99