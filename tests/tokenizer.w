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
    
    // we assert char is within ASCII bounds
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
