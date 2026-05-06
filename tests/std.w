// ==============================================================================
// std.w - Core Standard Library 
// ==============================================================================

// ---------------------------------------------------------
// 1. CONSTANTS & SYSTEM MEMORY MAPPING
// ---------------------------------------------------------
// Stack starts at 32768 (0x8000) and grows UP.
// We place utility workspaces and the heap top pointer safely above the stack.
@expr(50, TRUE)  : result = () : { result = 1; };
@expr(50, FALSE) : result = () : { result = 0; };
@expr(50, NULL)  : result = () : { result = 0; };

@expr(50, MMIO_PIXEL      ): result = () : { result = 65000; };
@expr(50, PRINT_WORKSPACE ): result = () : { result = 48900; };
@expr(50, DIV_WORKSPACE   ): result = () : { result = 49000; };
@expr(50, HEAP_START      ): result = () : { result = 49152; };


// ---------------------------------------------------------
// 2. INTRINSIC OPERATORS (Macros)
// ---------------------------------------------------------
// Note: We assign arguments to local vars (e.g., `val_a = a`) 
// to safely evaluate complex AST expressions exactly once before passing to @asm.

// Unary Operators
@expr(40, !, a) : result = (a) : {
    @asm(sltu, result, a, 1);
};
@expr(40, -, a) : result = (a) : {
    @asm(sub, result, x0, a);
};

// Binary Math
@expr(40, a, +, b) : result = (a, b) : { 
    @asm(add, result, a, b) ;
};
@expr(40, a, -, b) : result = (a, b) : { 
    @asm(sub, result, a, b) ;
};

// Bitwise Logic
@expr(20, a, |, b) : result = (a, b) : { 
    @asm(or_, result, a, b) ;
};
@expr(25, a, &, b) : result = (a, b) : { 
    @asm(and_, result, a, b) ;
};
@expr(30, a, ^, b ): result = (a, b) : { 

    @asm(xor, result, a, b) ;
};

// Comparisons
@expr(30, a < b) : result = (a, b) : { 
    val_a = a; val_b = b; @asm(slt, result, val_a, val_b) ;
};
@expr(30, a > b) : result = (a, b) : { 
    val_a = a; val_b = b; @asm(slt, result, val_b, val_a) ;
};
@expr(30, a == b) : result = (a, b) : { 
    val_a = a; val_b = b;
    tmp = val_a ^ val_b;
    @asm(sltiu, result, tmp, 1) ;
};
@expr(30, a != b) : result = (a, b) : { 
    val_a = a; val_b = b;
    tmp = val_a ^ val_b;
    @asm(sltu, result, x0, tmp) ;
};
@expr(30, a <= b) : result = (a, b) : { 
    val_a = a; val_b = b;
    tmp = val_b < val_a;
    @asm(xori, result, tmp, 1) ;
};
@expr(30, a >= b) : result = (a, b) : { 
    val_a = a; val_b = b;
    tmp = val_a < val_b;
    @asm(xori, result, tmp, 1) ;
};

// Memory Operations
read_byte : result = (ptr) : { 
    val_ptr = ptr;
    @asm(lbu, result, val_ptr, 0) ;
};
write_byte : [ptr] = (ptr, val) : { 
    @asm(sb, ptr, 0, val);
};

// Array offset calculation (words: base + i * 4)
arr_addr : result = (ptr, i) : {
    offset = i+i+i+i;
    result = ptr + offset;
};


// ---------------------------------------------------------
// 3. MEMORY ALLOCATOR
// ---------------------------------------------------------
// Global Bump Allocator. Keeps track of the frontier inside HEAP_START.
malloc : ptr = (size) : {
    heap_meta = HEAP_START;
    current = [heap_meta];
    
    cond_init = current == 0;
    (cond_init) : {
        current = HEAP_START + 4;
        cond_init = 0;
    };
    
    ptr = current;
    next_heap = current + size[heap_meta] = next_heap;
};

memcpy : result = (dest, src, size) : {
    i = 0;
    cond = i < size;
    (cond) : {
        curr_d = dest + i;
        curr_s = src + i;
        b = read_byte(curr_s);
        write_byte(curr_d, b);
        i = i + 1;
        cond = i < size;
    }
    result = dest;
};


// ---------------------------------------------------------
// 4. MATH UTILITIES
// ---------------------------------------------------------

// Shift-free fast division (O(log N))
div : q = (n, d) : {
    q = 0;
    r = n;
    // Static workspace to prevent malloc leaks on thousands of calls
    div_stack = DIV_WORKSPACE ;
    
    curr_d = d;
    i = 0;
    
    cond_build = curr_d <= r;
    (cond_build) : {
        [arr_addr(div_stack, i)] = curr_d;
        curr_d = curr_d + curr_d;
        i = i + 1;
        
        // Overflow safety escape latch
        cond_build_inner = curr_d > 0;
        (cond_build_inner) : {
            cond_build = curr_d <= r;
            cond_build_inner = 0;
        };
        cond_stop = curr_d <= 0;
        (cond_stop) : {
            cond_build = 0;
            cond_stop = 0;
        };
    };
    
    cond_apply = i > 0;
    (cond_apply) : {
        i = i - 1;
        val_d = [arr_addr(div_stack, i)];
        q = q + q;
        
        cond_sub = r >= val_d;
        (cond_sub) : {
            r = r - val_d;
            q = q + 1;
            cond_sub = 0;
        };
        cond_apply = i > 0;
    };
};

mul10 : result = (a) : {
    a2 = a + a;
    a4 = a2 + a2;
    a8 = a4 + a4;
    result = a8 + a2;
};


// ---------------------------------------------------------
// 5. I/O & STRINGS
// ---------------------------------------------------------
print_char : result = (c) : {
    ptr = MMIO_PIXEL;
    [ptr] = c;
    result = c;
};

print_newline : result = () : {
    print_char(10);
    result = 0;
};

print_str : result = (str) : {
    i = 0;
    cond = 1;
    (cond) : {
        curr = str + i;
        b = read_byte(curr);
        
        cond_stop = b == 0;
        (cond_stop) : { 
            cond = 0; 
            cond_stop = 0 ;
        };
        
        cond_cont = b != 0;
        (cond_cont) : {
            print_char(b);
            i = i + 1;
            cond_cont = 0;
        };
    };
    result = 0;
};

print_int : result = (val) : {
    temp = val;
    
    cond_zero = temp == 0;
    (cond_zero) : { 
        print_char(48); 
        cond_zero = 0 ;
    };
    
    digits = PRINT_WORKSPACE;
    count = 0;
    
    cond_run = temp > 0;
    (cond_run) : {
        q = div(temp, 10);
        qd = mul10(q);
        rem = temp - qd;
        
        digit_char = rem + 48;
        curr_ptr = digits + count;
        write_byte(curr_ptr, digit_char);
        
        count = count + 1;
        temp = q;
        cond_run = temp > 0;
    };
    
    cond_print = count > 0;
    (cond_print) : {
        count = count - 1;
        curr_ptr = digits + count;
        b = read_byte(curr_ptr);
        print_char(b);
        cond_print = count > 0;
    };
    result = 0;
}

streq : result = (s1, s2) : {
    result = 1;
    i = 0;
    cond = 1;
    (cond) : {
        curr1 = s1 + i;
        curr2 = s2 + i;
        b1 = read_byte(curr1);
        b2 = read_byte(curr2);
        
        cond_fail = b1 != b2;
        (cond_fail) : { 
            result = 0; 
            cond = 0; 
            cond_fail = 0;
        };
        
        cond_end = b1 == 0;
        (cond_end) : { 
            cond = 0;
            cond_end = 0 ;
        };
        i = i + 1;
    };
};


// ---------------------------------------------------------
// 6. COMPILER BOOTSTRAP UTILITIES
// ---------------------------------------------------------
// These tools enable text parsing necessary to build an AST.

is_digit : result = (c) : {
    c1 = c >= 48;
    c2 = c <= 57;
    result = c1 & c2;
};

is_alpha : result = (c) : {
    upper1 = c >= 65;
    upper2 = c <= 90;
    upper = upper1 & upper2;
    
    lower1 = c >= 97;
    lower2 = c <= 122;
    lower = lower1 & lower2;
    
    result = upper | lower;
};

// Advances pointer past ' ', \n, \t, \r
skip_whitespace : next_ptr = (str) : {
    i = 0;
    cond = 1;
    (cond) : {
        curr = str + i;
        b = read_byte(curr);
        
        is_space = b == 32;
        is_tab = b == 9;
        is_nl = b == 10;
        is_cr = b == 13;
        
        s1 = is_space | is_tab;
        s2 = is_nl | is_cr;
        is_ws = s1 | s2;
        
        cond_ws = is_ws == 1;
        (cond_ws) : { 
            i = i + 1; 
            cond_ws = 0 ;
        };
        
        cond_end = is_ws == 0;
        (cond_end) : { 
            cond = 0; 
            cond_end = 0; 
        };
    };
    next_ptr = str + i;
};

// Create an AST Node layout struct seamlessly via memory offsets
make_node : node = (type, value, left, right) : {
    node = malloc(16)[arr_addr(node, 0)] = type;
    [arr_addr(node, 1)] = value[arr_addr(node, 2)] = left;
    [arr_addr(node, 3)] = right;
};