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
    platform.asm.source_map = {} 
    platform.asm.current_user_line = "?"
    
    # 5-Pass Compilation using the Workspace implementation (Now with Native Comptime)
    workspace = compiler.Workspace(cpu_lib=lib, cpu_state_type=RiscVState)
    compiled_asm = workspace.compile_project(filepath)
    
    return compiled_asm.get_binary(), platform.asm.source_map



def print_debugger_dashboard(cpu_state, disasm_map, source_map):
    CYAN, GREEN, YELLOW, RESET, BOLD = '\033[96m', '\033[92m', '\033[93m', '\033[0m', '\033[1m'

    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{CYAN}--- REGISTERS ---{RESET}")
    for i in range(0, 32, 4):
        print(f"x{i:<2}: {cpu_state.regs[i]:08x}   x{i+1:<2}: {cpu_state.regs[i+1]:08x}   "
              f"x{i+2:<2}: {cpu_state.regs[i+2]:08x}   x{i+3:<2}: {cpu_state.regs[i+3]:08x}")
        
    print(f"{CYAN}--- CONTEXT ---{RESET}")
    pc = cpu_state.pc
    pcs = sorted(disasm_map.keys())
    
    try:
        idx = pcs.index(pc)
    except ValueError:
        idx = -1
        
    if idx != -1:
        # Show 2 previous instructions, the current instruction, and 3 future instructions
        start_idx = max(0, idx - 2)
        end_idx = min(len(pcs), idx + 4)
        for i in range(start_idx, end_idx):
            curr_pc = pcs[i]
            inst_str = disasm_map[curr_pc]
            src_info = source_map.get(curr_pc, {})
            
            c_info = src_info.get("compiler", "")
            u_info = src_info.get("user_source", "?")
            meta = f"[{u_info} | {c_info}]"
            
            if curr_pc == pc:
                print(f"{GREEN}>> {inst_str:<38} {YELLOW}{meta}{RESET}")
            else:
                print(f"   {inst_str:<38} {meta}")
    else:
        print(f"{GREEN}>> PC: 0x{pc:04x} (Halted or Unknown){RESET}")
    print(f"{BOLD}{'='*80}{RESET}")


def run_program(lib, RiscVState, filepath, debug=False):
    print(f"\n{'='*40}\nRunning: {filepath} (Debug: {debug})\n{'='*40}")
    
    try:
        program_bytes, source_map = compile_file(filepath, lib, RiscVState)
    except Exception as e:
        print(f"Compilation failed for {filepath}: {e}")
        traceback.print_exc()
        return
    
    bin_filename = filepath.replace(".w", ".bin")
    with open(bin_filename, "wb") as f:
        f.write(program_bytes)
    
    disasm_map = disasm.disassemble(program_bytes)
    if not debug:
        for item in disasm_map:
            print(item)
        
    cpu_state = RiscVState()
    lib.init_cpu(ctypes.byref(cpu_state))
    for i, byte in enumerate(program_bytes):
        cpu_state.memory[i] = byte
        
    cycles = 0
    cpu_state.memory[65000] = 255 
    step_mode = debug

    while not cpu_state.halt and cycles < 1000000:
        if step_mode:
            print_debugger_dashboard(cpu_state, disasm_map, source_map)
            while True:
                cmd = input("(dbg)> ").strip().split()
                if not cmd: 
                    break # Step 1 cycle
                elif cmd[0] == 'c':
                    step_mode = False # Disable stepping, continue
                    break
                elif cmd[0] == 'q':
                    return
                elif cmd[0] == 'm':
                    if len(cmd) >= 2:
                        try:
                            addr = int(cmd[1], 0)
                            count = int(cmd[2], 0) if len(cmd) >= 3 else 1
                            for i in range(count):
                                val = cpu_state.memory[addr + i]
                                print(f"Mem[0x{addr+i:04x}] = 0x{val:02x} ({val})")
                        except ValueError: 
                            print("Invalid address format.")
                    else:
                        print("Usage: m <address> [count] (e.g. m 0x1000 4)")
                else:
                    print("Commands: [Enter] step, c continue, m memory <addr>, q quit")
                    
        lib.run_cycles(ctypes.byref(cpu_state), 1)
        cycles += 1
        
        val = cpu_state.memory[65000]
        if val != 255:
            prefix = "[IO] >>" if step_mode else f"[{cycles} cycles]"
            print(f"\n{prefix} Memory[65000] received value: {val}")
            cpu_state.memory[65000] = 255

    print(f"\nExecution finished in {cycles} cycles.")

def main():
    lib, RiscVState = load_cpu_lib()
    if not lib:
        return
    
    debug_mode = "--debug" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--debug"]
    
    if args:
        run_program(lib, RiscVState, args[0], debug=debug_mode)
        return

    test_files = sorted(glob.glob("tests/*.w"))
    for test_file in test_files:
        run_program(lib, RiscVState, test_file, debug=debug_mode)

if __name__ == "__main__":
    main()