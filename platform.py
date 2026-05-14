from asm import RiscVAssembler

# Create the assembler
asm = RiscVAssembler()
#expected registers
x0 = 0       
ra = 1      
t0 = 5      
t1 = 6       
t2 = 7      
t3 = 28      
a1 = 11
a7 = 17     
fp = 8
sp = 2
a0 = 10
reg_map = {f"x{i}": i for i in range(32)}
reg_map.update({
    "zero": 0, "ra": 1, "sp": 2, "gp": 3, "tp": 4,
    "t0": 5, "t1": 6, "t2": 7, "s0": 8, "fp": 8, "s1": 9,
    "a0": 10, "a1": 11, "a2": 12, "a3": 13, "a4": 14, "a5": 15, "a6": 16, "a7": 17,
    "s2": 18, "s3": 19, "s4": 20, "s5": 21, "s6": 22, "s7": 23, "s8": 24, "s9": 25, "s10": 26, "s11": 27,
    "t3": 28, "t4": 29, "t5": 30, "t6": 31
})

imm_positions = {
    "lui": {1}, "jal": {1}, "jalr": {2},
    "beq": {2}, "bne": {2}, "bge": {2},
    "lw": {2}, "lbu": {2},
    "sw": {1}, "sb": {1},
    "addi": {2}, "xori": {2}, "ori": {2}, "andi": {2}, "sltiu": {2},
}

no_rd_instructions = {"store", "sw", "sb", "bge", "blt", "bgeu", "bltu", "beq", "bne", "ecall", "label"}                

REGISTER_SIZE = asm.REGISTER_SIZE 

stack_ptr = 2 
stack_start = 0x8000 
stack_incr = REGISTER_SIZE

current_stack_slots = 0
scope_depths = []

def start_scope():
    scope_depths.append(current_stack_slots)

def get_scope_pushed():
    if scope_depths:
        return current_stack_slots - scope_depths[-1]
    return 0

def abandon_scope():
    if scope_depths:
        scope_depths.pop()


def end_scope(returns=0):
    global current_stack_slots
    assert scope_depths, "No active scope to end"
    start_depth = scope_depths.pop()
    
    diff = current_stack_slots - start_depth - returns
    assert diff >= 0, f"Scope physics violation: Ending scope requires clearing {diff} slots, which indicates memory corruption or missing pops."

    if diff > 0:
        if returns > 0:
            for i in range(returns):
                offset_from_top = (returns - i) * REGISTER_SIZE
                asm.lw(t0, stack_ptr, -offset_from_top)
                
                offset_to_write = (diff + returns - i) * REGISTER_SIZE
                asm.sw(stack_ptr, -offset_to_write, t0)
        shrink_stack(diff)
    elif diff < 0:
        assert False, f"Stack underflow in scope! Expected at least {start_depth + returns}, got {current_stack_slots}"

def init():
    global current_stack_slots
    current_stack_slots = 0
    scope_depths.clear()
    load_immediate(stack_ptr, stack_start)

def push(reg):
    global current_stack_slots
    asm.sw(stack_ptr, 0, reg)                
    asm.addi(stack_ptr, stack_ptr, stack_incr)
    current_stack_slots += 1

def pop(reg):
    global current_stack_slots
    assert current_stack_slots > 0, \
        f"Compiler Stack Tracking Underflow! Attempted to generate pop({reg}) on an empty stack structure."
     
    asm.addi(stack_ptr, stack_ptr, -stack_incr)  
    asm.lw(reg, stack_ptr, 0)                  
    current_stack_slots -= 1

def shrink_stack(slots_count):
    global current_stack_slots
    
    assert slots_count >= 0, f"Cannot dynamically shrink stack by a negative slot count: {slots_count}"
    assert current_stack_slots >= slots_count, \
        f"Compiler Stack Tracking Underflow! Attempted to shrink ({slots_count}) slots with only ({current_stack_slots}) left."
    
    asm.addi(stack_ptr, stack_ptr, -(slots_count * REGISTER_SIZE))
    current_stack_slots -= slots_count

def peek(reg):
    asm.lw(reg, stack_ptr, -stack_incr)

def load_immediate(reg, val):
    if -2048 <= val <= 2047:
        asm.addi(reg, x0, val)
        return
    lo = val & 0xFFF
    hi = val >> 12
    if lo & 0x800:
        hi += 1
    asm.lui(reg, hi)
    asm.addi(reg, reg, lo)

def push_value(value):
    load_immediate(t0, value)
    push(t0)

def push_static(addr):
    asm.lw(t0, addr, 0)
    push(t0)

def pop_static(addr):
    pop(t0)
    asm.sw(addr, 0, t0)

def push_mem():
    pop(t0)
    push_static(t0)

def pop_mem():
    pop(t0)
    pop(t1)
    asm.sw(t0, 0, t1)

# ---- Backend Abstraction Interface ----

def get_safe_regs():
    return [18, 19, 20, 21, 22, 23, 24, 25]

# TODO count and assert should probably be done for all of these.
# possibly even a stack alloc incase you run out of registers.
# you could then use registers everywhere and bleed into stack when needed.
def get_temp_regs_for_tco(count):
    regs = [5, 6, 7, 28, 29, 30, 31, 10, 11, 12, 13, 14, 15, 16, 17]
    assert count <= len(regs), f"TCO Compilation Limit Exceeded: Requires {count} concurrent argument registers, system provides only {len(regs)}."
    return regs[:count]

def get_temp_regs_for_asm():
    return [6, 7, 28, 29, 30, 31]

def read_local(dest_reg, fp_offset_slots, name=""):
    byte_offset = fp_offset_slots * REGISTER_SIZE
    asm.lw(dest_reg, reg_map["fp"], byte_offset)

def write_local(fp_offset_slots, src_reg, name=""):
    byte_offset = fp_offset_slots * REGISTER_SIZE
    asm.sw(reg_map["fp"], byte_offset, src_reg)

def read_relative(dest_reg, relative_slot_offset):
    asm.lw(dest_reg, stack_ptr, relative_slot_offset * REGISTER_SIZE)

def write_relative(relative_slot_offset, src_reg):
    asm.sw(stack_ptr, relative_slot_offset * REGISTER_SIZE, src_reg)

def jump(label_name):
    asm.jal(x0, label_name)

def call(label_name):
    asm.jal(ra, label_name)

def jump_and_link(dest_reg, label_name):
    asm.jal(dest_reg, label_name)

def return_jump():
    asm.jalr(x0, ra, 0)

def label(name):
    asm.label(name)

def branch_not_equal(rs1, rs2, target_label):
    asm.bne(rs1, rs2, target_label)

def system_call():
    asm.ecall()

def halt():
    emit_instruction("addi", 17, 0, 0)
    asm.ecall()

def store_deref(addr_reg, src_reg):
    asm.sw(addr_reg, 0, src_reg)

def load_deref(dest_reg, addr_reg):
    asm.lw(dest_reg, addr_reg, 0)

def emit_bytes(data):
    asm.code.extend(data)

def emit_aligned_bytes(data):
    emit_bytes(data)
    padding = (REGISTER_SIZE - (len(data) % REGISTER_SIZE)) % REGISTER_SIZE
    if padding > 0:
        emit_bytes(b'\x00' * padding)

def emit_instruction(inst_name, *args):
    asm_method = getattr(asm, inst_name)
    if asm_method is None:
        raise ValueError(f"Unknown instruction: {inst_name}")
    asm_method(*args)

def is_mutating_instruction(inst_name):
    return inst_name in {"store", "sw", "sb"}

def is_volatile_instruction(inst_name):
    return inst_name in no_rd_instructions

def is_branch_target(inst_name, arg_index, num_args):
    branches = {"jal", "bge", "blt", "bgeu", "bltu", "beq", "bne", "label"}
    return inst_name in branches and arg_index == num_args - 1

def is_immediate_arg(inst_name, arg_index):
    return inst_name in imm_positions and arg_index in imm_positions[inst_name]

def is_register(name):
    return name in reg_map

def get_register(name):
    return reg_map[name]

def has_rd_register(inst_name):
    return inst_name not in no_rd_instructions

def reset_assembler():
    global current_stack_slots
    asm.code = bytearray()
    asm.labels = {}
    asm.fixups = {}
    asm.pc = 0
    current_stack_slots = 0
    scope_depths.clear()

def get_binary():
    return asm.get_binary()

def get_code_length():
    return len(asm.code)