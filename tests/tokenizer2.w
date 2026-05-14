@import(tests/std.w);

@using(bool);
@using(int);
@using(sys);

SOURCE_PTR = 1000;
MAX_LEN = 32000;

mul10 : out[int] = (val[int]) : {
    @asm(slli, t0, val, 3);
    @asm(slli, t1, val, 1);
    @asm(add, out, t0, t1);
};
mul16 : out[int] = (val[int]) : { @asm(slli, out, val, 4); };
mul2 : out[int] = (val[int]) : { @asm(slli, out, val, 1); };

read_byte : val[int] = (ptr[int]) : {
    @asm(lbu, val, ptr, 0); 
};


itoa_loop : len[int] = (0, val[int], ptr[int], count[int]) : {
    len = count;
};
itoa_loop : len[int] = (1, val[int], ptr[int], count[int]) : {
    len = count;
    ten = 10;
    digit = val % ten;
    next_val = val / ten;
    
    [ptr - 1] = digit + 48; // Convert to ASCII character
    len = itoa_loop(val > 0,next_val, ptr - 1, count + 1); // Native TCO
};
print_int_inline : _ = (val[int]) : {
    buf_ptr = 50000; // Safe memory region
    if (val == 0) {
        .zero = "0";
        sys.write(.zero[0], .zero[1]);
    };
    if (val != 0) {
        len = itoa_loop(1, val, buf_ptr + 10, 0);
        sys.write(buf_ptr + 10 - len, len);
    };
};

// --- Formatted Output via String Embeds ---

print_token_int : _ = (type[int], line[int], col[int], val[int]) : {
    .colon = ":";
    .nl = "\n";
    
    print_int_inline(type); sys.write(.colon[0], .colon[1]);
    print_int_inline(line); sys.write(.colon[0], .colon[1]);
    print_int_inline(col);  sys.write(.colon[0], .colon[1]);
    print_int_inline(val);  sys.write(.nl[0], .nl[1]);
};

print_token_str : _ = (type[int], line[int], col[int], ptr[int], len[int]) : {
    .colon = ":";
    .nl = "\n";
    
    print_int_inline(type); sys.write(.colon[0], .colon[1]);
    print_int_inline(line); sys.write(.colon[0], .colon[1]);
    print_int_inline(col);  sys.write(.colon[0], .colon[1]);
    if (len > 0) { sys.write(ptr, len); };
    sys.write(.nl[0], .nl[1]);
};


// --- Flat Character Classes ---

is_alpha_char : res[bool] = (c[int]) : {
    res = 0;
    if (c == 95) { res = 1; }; // '_'
    if (c >= 65) { if (c <= 90) { res = 1; }; }; // A-Z
    if (c >= 97) { if (c <= 122) { res = 1; }; }; // a-z
};

is_digit_char : res[bool] = (c[int]) : {
    res = 0;
    if (c >= 48) { if (c <= 57) { res = 1; }; }; // 0-9
};

is_whitespace : res[bool] = (c[int]) : {
    res = 0;
    if (c == 32) { res = 1; };
    if (c == 10) { res = 1; };
    if (c == 9)  { res = 1; };
    if (c == 13) { res = 1; };
};

is_valid_symbol : res[bool] = (c[int]) : {
    res = 0;
    if (c == 61) { res = 1; }; // =
    if (c == 33) { res = 1; }; // !
    if (c == 60) { res = 1; }; // <
    if (c == 62) { res = 1; }; // >
    if (c == 42) { res = 1; }; // *
    if (c == 40) { res = 1; }; // (
    if (c == 41) { res = 1; }; // )
    if (c == 94) { res = 1; }; // ^
    if (c == 47) { res = 1; }; // /
    if (c == 43) { res = 1; }; // +
    if (c == 45) { res = 1; }; // -
    if (c == 124) { res = 1; };// |
    if (c == 38) { res = 1; }; // &
    if (c == 91) { res = 1; }; // [
    if (c == 93) { res = 1; }; // ]
    if (c == 123) { res = 1; };// {
    if (c == 125) { res = 1; };// }
    if (c == 58) { res = 1; }; // :
    if (c == 59) { res = 1; }; // ;
    if (c == 44) { res = 1; }; // ,
    if (c == 46) { res = 1; }; // .
    if (c == 64) { res = 1; }; // @
    if (c == 63) { res = 1; }; // ?
};

// --- Lexer Sub-Loop Parsers ---

consume_comment : length[int] = (ptr[int], len[int], max_ptr[int]) : {
    length = len;
    if ((ptr + len) < max_ptr) {
        c = read_byte(ptr + len);
        if (c != 10) { length = consume_comment(ptr, len + 1, max_ptr); };
    };
};

parse_string : length[int] = (ptr[int], len[int], max_ptr[int]) : {
    length = len;
    if ((ptr + len) < max_ptr) {
        c = read_byte(ptr + len);
        if (c != 34) { length = parse_string(ptr, len + 1, max_ptr); };
        if (c == 34) { length = len + 1; }; 
    };
};

// Base Case (Hit max_ptr OR hit invalid character)
_consume_ident_loop : length[int] = (1, ptr[int], len[int], max_ptr[int]) : {
    length = len;
};

// Recursive Step
_consume_ident_loop : length[int] = (0, ptr[int], len[int], max_ptr[int]) : {
    c = read_byte(ptr + len);
    is_valid = is_alpha_char(c) || is_digit_char(c); // using your || macro
    
    next_len = len;
    if (is_valid) { next_len = len + 1; };
    
    // Evaluate stop conditions for the next loop
    hit_max = (ptr + next_len) == max_ptr;
    is_done = !is_valid || hit_max;

    // Guaranteed TCO
    length = _consume_ident_loop(is_done, ptr, next_len, max_ptr);
};

// Wrapper
consume_ident : length[int] = (ptr[int], len[int], max_ptr[int]) : {
    hit_max = (ptr + len) == max_ptr;
    length = _consume_ident_loop(hit_max, ptr, len, max_ptr);
};

parse_dec : val[int], length[int] = (ptr[int], len[int], max_ptr[int], current_val[int]) : {
    val = current_val;
    length = len;
    if ((ptr + len) < max_ptr) {
        c = read_byte(ptr + len);
        is_dig = is_digit_char(c);
        
        if (c == 95) { val, length = parse_dec(ptr, len + 1, max_ptr, current_val); };
        if (is_dig) { 
            val, length = parse_dec(ptr, len + 1, max_ptr, mul10(current_val) + (c - 48)); 
        };
    };
};

parse_hex : val[int], length[int] = (ptr[int], len[int], max_ptr[int], current_val[int]) : {
    val = current_val;
    length = len;
    if ((ptr + len) < max_ptr) {
        c = read_byte(ptr + len);
        is_num = is_digit_char(c);
        
        if (c == 95) { val, length = parse_hex(ptr, len + 1, max_ptr, current_val); };
        if (is_num) { val, length = parse_hex(ptr, len + 1, max_ptr, mul16(current_val) + (c - 48)); };
        if (c >= 97) { if (c <= 102) { val, length = parse_hex(ptr, len + 1, max_ptr, mul16(current_val) + (c - 87)); }; };
        if (c >= 65) { if (c <= 70) { val, length = parse_hex(ptr, len + 1, max_ptr, mul16(current_val) + (c - 55)); }; };
    };
};

parse_bin : val[int], length[int] = (ptr[int], len[int], max_ptr[int], current_val[int]) : {
    val = current_val;
    length = len;
    if ((ptr + len) < max_ptr) {
        c = read_byte(ptr + len);
        if (c == 95) { val, length = parse_bin(ptr, len + 1, max_ptr, current_val); };
        if (c == 48) { val, length = parse_bin(ptr, len + 1, max_ptr, mul2(current_val)); };
        if (c == 49) { val, length = parse_bin(ptr, len + 1, max_ptr, mul2(current_val) + 1); };
    };
};


// --- Core State Machine Loop ---

parse_loop : _ = (1, ptr[int], max_ptr[int], line[int], col[int]) : {
    .eof = "EOF";
    print_token_str(5, line, col, .eof[0], .eof[1]); // 5 = EOF type
};

parse_loop : _ = (0, ptr[int], max_ptr[int], line[int], col[int]) : {
    c = read_byte(ptr);
    
    len = 0;
    matched = 0;

    // 1. Whitespace
    is_ws = is_whitespace(c);
    if (is_ws) {
        matched = 1;
        len = 1;
        next_line = line;
        if (c == 10) { next_line = line + 1; };
        next_col = col + 1;
        if (c == 10) { next_col = 1; };
        
        _ = parse_loop((ptr + 1) == max_ptr, ptr + 1, max_ptr, next_line, next_col);
    };

    // 2. Comments
    if (!matched) {
        if (c == 47) { // '/'
            if ((ptr + 1) < max_ptr) {
                c2 = read_byte(ptr + 1);
                if (c2 == 47) {
                    matched = 1;
                    len = consume_comment(ptr, 2, max_ptr);
                    _ = parse_loop((ptr + len) == max_ptr, ptr + len, max_ptr, line, col + len);
                };
            };
        };
    };

    // 3. Digits
    if (!matched) {
        is_dig = is_digit_char(c);
        if (is_dig) {
            matched = 1;
            is_hex = 0;
            is_bin = 0;
            if (c == 48) {
                if ((ptr + 1) < max_ptr) {
                    c2 = read_byte(ptr + 1);
                    if (c2 == 120) { is_hex = 1; }; // x
                    if (c2 == 98) { is_bin = 1; };  // b
                };
            };

            if (is_hex) {
                val, len = parse_hex(ptr, 2, max_ptr, 0);
                print_token_int(3, line, col, val);
            };
            if (is_bin) {
                val, len = parse_bin(ptr, 2, max_ptr, 0);
                print_token_int(3, line, col, val);
            };
            
            is_other = 0;
            if (!is_hex) { if (!is_bin) { is_other = 1; }; };
            if (is_other) {
                val, len = parse_dec(ptr, 0, max_ptr, 0);
                print_token_int(3, line, col, val);
            };

            _ = parse_loop((ptr + len) == max_ptr, ptr + len, max_ptr, line, col + len);
        };
    };

    // 4. Strings
    if (!matched) {
        if (c == 34) {
            matched = 1;
            len = parse_string(ptr, 1, max_ptr);
            print_token_str(4, line, col, ptr + 1, len - 2); 
            _ = parse_loop((ptr + len) == max_ptr, ptr + len, max_ptr, line, col + len);
        };
    };

    // 5. Identifiers
    if (!matched) {
        is_a = is_alpha_char(c);
        if (is_a) {
            matched = 1;
            len = consume_ident(ptr, 1, max_ptr);
            print_token_str(2, line, col, ptr, len);
            _ = parse_loop((ptr + len) == max_ptr, ptr + len, max_ptr, line, col + len);
        };
    };

    // 6. Symbols
    if (!matched) {
        is_sym = is_valid_symbol(c);
        if (is_sym) {
            matched = 1;
            len = 1;
            if ((ptr + 1) < max_ptr) {
                c2 = read_byte(ptr + 1);
                if (c2 == 61) {
                    if (c == 61) { len = 2; }; // ==
                    if (c == 33) { len = 2; }; // !=
                    if (c == 60) { len = 2; }; // <=
                    if (c == 62) { len = 2; }; // >=
                };
            };
            print_token_str(1, line, col, ptr, len);
            _ = parse_loop((ptr + len) == max_ptr, ptr + len, max_ptr, line, col + len);
        };
    };

    // Panic Trap
    if (!matched) {
        .err = "Syntax Error Triggered\n";
        sys.write(.err[0], .err[1]);
        assert(0); 
    };
};


// --- Execution Entry ---
bytes_read = sys.read_stdin(SOURCE_PTR, MAX_LEN);
assert(bytes_read > 0);

end_ptr = SOURCE_PTR + bytes_read;
_ = parse_loop(0, SOURCE_PTR, end_ptr, 1, 1);