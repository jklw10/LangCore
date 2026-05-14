import ctypes
import os
import glob
import traceback
import platform
import compiler
import disasm 
import sys

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

    lib.init_cpu.argtypes =[ctypes.POINTER(RiscVState)]
    lib.run_cycles.argtypes =[ctypes.POINTER(RiscVState), ctypes.c_uint32]
    
    return lib, RiscVState

def compile_file(filepath, lib, RiscVState):
    """Compiles a single .w file and returns the binary."""
    # Reset the global assembler state
    platform.asm.code = bytearray()
    platform.asm.labels = {}
    platform.asm.fixups = {}
    platform.asm.pc = 0
    
    # 5-Pass Compilation using the Workspace implementation (Now with Native Comptime)
    workspace = compiler.Workspace(cpu_lib=lib, cpu_state_type=RiscVState)
    compiled_asm = workspace.compile_project(filepath)
    
    return compiled_asm.get_binary()

def run_program(lib, RiscVState, filepath):
    """Runs a compiled binary in the emulator."""
    print(f"\n{'='*40}")
    print(f"Running: {filepath}")
    print(f"{'='*40}")
    
    try:
        program_bytes = compile_file(filepath, lib, RiscVState)
    except Exception as e:
        print(f"Compilation failed for {filepath}: {e}")
        traceback.print_exc()
        return
    
    bin_filename = filepath.replace(".w", ".bin")
    with open(bin_filename, "wb") as f:
        f.write(program_bytes)
    print(f"Saved binary to {bin_filename}")
    
    disasm.disassemble(program_bytes)
    
    cpu_state = RiscVState()
    lib.init_cpu(ctypes.byref(cpu_state))
    
    for i, byte in enumerate(program_bytes):
        cpu_state.memory[i] = byte
        
    cycles = 0
    cpu_state.memory[65000] = 255 

    while not cpu_state.halt and cycles < 100000:
        lib.run_cycles(ctypes.byref(cpu_state), 1)
        cycles += 1
        
        val = cpu_state.memory[65000]
        if val != 255:
            print(f"[{cycles} cycles] Memory[65000] received value: {val}")
            cpu_state.memory[65000] = 255

    print(f"\nExecution finished in {cycles} cycles.")
    print(f"Final SP (x2): 0x{cpu_state.regs[2]:08x}")
    
    if cpu_state.regs[10] != 0:
        print(f"Final a0 (x10): {cpu_state.regs[10]}")

def main(args):
    lib, RiscVState = load_cpu_lib()
    if not lib:
        return
    
    if args is not None:
        run_program(lib, RiscVState, args)
        return

    test_files = sorted(glob.glob("tests/*.w"))
    if not test_files:
        print("No .w files found. Save some test scripts in this directory.")
        return
        
    for test_file in test_files:
        run_program(lib, RiscVState, test_file)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)