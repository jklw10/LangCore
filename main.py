import ctypes
import os
import glob

import traceback
import macros
import AST
import compiler
import tokens
import disasm 
"""
LANGUAGE DESIGN PHILOSOPHY & SPECIFICATION:
No Primitive Types: 
   The compiler natively has no concept of `int`, `float`, or `bool`. 
   The implicit default type is raw memory (`bytes`).

Types are Comptime Memory Slices: 
   A "Type" is simply an alias for an allocation size on the stack. 
   Example: `int = (bytes[:4])` tells the compiler to allocate 4 bytes.
   
   This should enable typed pointer's benefits?.

Library-Defined Operations: 
   Operators (+, -, *, ==) are not built-in. They are syntactic sugar for 
   type methods (e.g., `value.@op(+)`). The Standard Library defines these 
   using inline `@asm` mapped to raw CPU instructions.


Data Movement (:) vs. Mutation (=):
   `:` denotes value movement, type aliasing, or passing data across scopes.
     it is "to", "0:4" = "0 to 4", (in):{ctx}:res, is a pipeline definition.
   `=` denotes explicit identity assignment and runtime memory mutation.
     it is "is", "res = 4"

The Universal Pipeline Construct: 
   There is syntactically no distinction between functions, loops, namespaces, 
   and type definitions. They are all structural variants of a Universal Pipeline.
   Format: `return = (bindings) : { body } `

   
Data-Driven Control Flow (Zero-Keyword Branching):
   The language contains ZERO native control flow keywords (`if`, `while`, `else`).
   Conditional branching is an emergent property of temporal pipelines (loops). 
   An "if statement" is simply a loop pipeline constrained to execute 0 or 1 times 
   based on a dynamic truth condition (e.g., `( c = 0 : condition ) : { ... }`).
   
Pre-Declaration & Zero-Initialization:
   Declaring a typed variable at a block boundary (e.g., `res[int] = ... : { }`) 
   allocates and zero-initializes it in the outer scope, allowing inner 
   blocks to mutate it explicitly without scope-popping issues.

Raw Memory & Unsafe Transparency:
   The language operates as an ultra-high-level macro assembler. Direct 
   memory dereferencing (`[ptr]`), pointer arithmetic, and transparent 
   bridging to CPU registers via `@asm` are first-class workflows. Strings 
   do not exist natively; they are treated strictly as memory slices or 
   embedded binaries.

Explicit mutation:
  No hidden mutations, aka no side effects without visibility

Pattern matching via multifunction:
  If a binding has x==value, it is now a pattern to match
  eg.
  match = {
    case:result = (x==1, y): {result = y*2}
    case:result = (x, y): {result = y}
  }
  match.case(0,1)

Caller is responsible for allocation.
A pipeline's only purpose is to transform data.
Aim to be rid of all keywords.

minimalist version (current impl)

@expr(9, a, ==, b) : out = (a, b) : {
    @asm(sub, out, a, b);
    @asm(sltiu, out, out, 1);
};

@expr(2, if, cond, t_body) : out = (cond, t_body) : {
    _run = cond;
    (_run) : {
        t_body;
        _run = 0; 
    };
};

these are possible.
"""

def load_cpu_lib():
    """Loads the RISC-V CPU C library."""
    lib_name = "cpu.dll" if os.name == 'nt' else "libcpu.so"
    if not os.path.exists(lib_name):
        print(f"Warning: {lib_name} not found. Ensure the C library is compiled.")
        return None, None
    
    lib = ctypes.CDLL(os.path.abspath(lib_name))

    class RiscVState(ctypes.Structure):
        _fields_ =[
            ("regs", ctypes.c_uint32 * 32),
            ("pc",   ctypes.c_uint32),
            ("memory", ctypes.c_uint8 * 65536),
            ("halt",   ctypes.c_bool),
        ]

    lib.init_cpu.argtypes = [ctypes.POINTER(RiscVState)]
    lib.run_cycles.argtypes =[ctypes.POINTER(RiscVState), ctypes.c_uint32]
    
    return lib, RiscVState

def compile_file(filepath):
    """Compiles a single .w file and returns the binary."""
    # Reset the global assembler state from macros to prevent code merging
    macros.asm.code = bytearray()
    macros.asm.labels = {}
    macros.asm.fixups = {}
    macros.asm.pc = 0
    
    with open(filepath, 'r') as f:
        source = f.read()
        
    test_tokens = tokens.tokenize(source)
    ast = AST.parse(test_tokens)
    comp = compiler.Compiler()
    
    # Returns the populated global RiscVAssembler
    compiled_asm = comp.compile(ast)
    return compiled_asm.get_binary()

def run_program(lib, RiscVState, filepath):
    """Runs a compiled binary in the emulator."""
    print(f"\n{'='*40}")
    print(f"Running: {filepath}")
    print(f"{'='*40}")
    
    try:
        program_bytes = compile_file(filepath)
    except Exception as e:
        print(f"Compilation failed for {filepath}: {e}")
        traceback.print_exc()
        return
    
    # 1. Output the raw binary for external tools (e.g. objdump)
    bin_filename = filepath.replace(".w", ".bin")
    with open(bin_filename, "wb") as f:
        f.write(program_bytes)
    print(f"Saved binary to {bin_filename}")
    
    # 2. Print human-readable Disassembly
    disasm.disassemble(program_bytes)
    
    cpu_state = RiscVState()
    lib.init_cpu(ctypes.byref(cpu_state))
    
    # Load program into memory
    for i, byte in enumerate(program_bytes):
        cpu_state.memory[i] = byte
        
    cycles = 0
    cpu_state.memory[65000] = 255 # Initialize with a dummy flag

    # Run loop
    while not cpu_state.halt and cycles < 100000:
        lib.run_cycles(ctypes.byref(cpu_state), 1)
        cycles += 1
        
        # Check simulated Memory-Mapped I/O at address 65000
        # Because we do word-stores (4 bytes), byte 65000 gets the integer value.
        val = cpu_state.memory[65000]
        if val != 255:
            print(f"[{cycles} cycles] Pixel ON! -> Memory[65000] received value: {val}")
            
            # Reset pixel so we can catch subsequent writes
            cpu_state.memory[65000] = 255

    print(f"\nExecution finished in {cycles} cycles.")
    print(f"Final SP (x2): 0x{cpu_state.regs[2]:08x}")
    
    # Print the return value register (a0 / x10) if you use it globally
    if cpu_state.regs[10] != 0:
        print(f"Final a0 (x10): {cpu_state.regs[10]}")

def main():
    lib, RiscVState = load_cpu_lib()
    if not lib:
        return
    
    test_files = sorted(glob.glob("tests/*.w"))
    
    if not test_files:
        print("No .w files found. Save some test scripts in this directory.")
        return
        
    for test_file in test_files:
        run_program(lib, RiscVState, test_file)

if __name__ == "__main__":
    main()
