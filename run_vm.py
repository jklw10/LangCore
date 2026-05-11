import sys
import ctypes
import os

def run_binary(bin_filepath):
    # 1. Load the C Library
    lib_name = "cpu.dll" if os.name == 'nt' else "libcpu.so"
    if not os.path.exists(lib_name):
        print(f"Error: {lib_name} not found in the current directory.")
        sys.exit(1)
        
    lib = ctypes.CDLL(os.path.abspath(lib_name))

    # 2. Define the exact C-struct mapping
    class RiscVState(ctypes.Structure):
        _fields_ =[
            ("regs", ctypes.c_uint32 * 32),
            ("pc",   ctypes.c_uint32),
            ("memory", ctypes.c_uint8 * 65536),
            ("halt",   ctypes.c_bool),
        ]

    lib.init_cpu.argtypes =[ctypes.POINTER(RiscVState)]
    lib.run_cycles.argtypes =[ctypes.POINTER(RiscVState), ctypes.c_uint32]
    
    # 3. Read the binary
    if not os.path.exists(bin_filepath):
        print(f"Error: Binary file '{bin_filepath}' not found.")
        sys.exit(1)
        
    with open(bin_filepath, "rb") as f:
        program_bytes = f.read()

    print(f"\n{'='*40}")
    print(f"Executing: {bin_filepath}")
    print(f"{'='*40}")

    # 4. Initialize VM Memory
    cpu_state = RiscVState()
    lib.init_cpu(ctypes.byref(cpu_state))
    
    if len(program_bytes) > len(cpu_state.memory):
        print("Error: Binary is too large for VM memory.")
        sys.exit(1)

    for i, byte in enumerate(program_bytes):
        cpu_state.memory[i] = byte
        
    cpu_state.memory[65000] = 255 # Initialize dummy I/O flag

    # 5. Execution Loop
    cycles = 0
    max_cycles = 500000 # Safety net
    
    while not cpu_state.halt and cycles < max_cycles:
        lib.run_cycles(ctypes.byref(cpu_state), 1)
        cycles += 1
        
        # Check simulated Memory-Mapped I/O at address 65000
        val = cpu_state.memory[65000]
        if val != 255:
            print(f"[{cycles} cycles] Memory[65000] received value: {val}")
            cpu_state.memory[65000] = 255 # Reset flag

    # 6. Output VM State
    print(f"\nExecution finished in {cycles} cycles.")
    print(f"Final SP (x2): 0x{cpu_state.regs[2]:08x}")
    
    if cpu_state.regs[10] != 0:
        print(f"Final a0 (x10): {cpu_state.regs[10]}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_vm.py <path_to_binary.bin>")
        sys.exit(1)
        
    run_binary(sys.argv[1])