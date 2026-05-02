const std = @import("std");

// --- 1. MEMORY LAYOUT ---
// Matches the Python ctypes structure exactly.
pub const CpuState = extern struct {
    regs: [32]u32, // x0-x31
    pc: u32, // Program Counter
    memory:[65536]u8, // 64KB RAM
    halted: bool, // Triggered by specific instruction (e.g., ECALL)
};
// Extract opcode (lowest 7 bits)
inline fn opcode(inst: u32) u32 {
    return inst & 0x7F;
}
// Extract destination register (bits 7-11)
inline fn registerDestination(inst: u32) u5 {
    return @as(u5, @truncate(inst >> 7));
}
// Extract source register 1 (bits 15-19)
inline fn registerSource1(inst: u32) u5 {
    return @as(u5, @truncate(inst >> 15));
}
// Extract source register 2 (bits 20-24)
inline fn registerSource2(inst: u32) u5 {
    return @as(u5, @truncate(inst >> 20));
}
// Extract function code 3 (bits 12-14)
inline fn funct3(inst: u32) u3 {
    return @as(u3, @truncate(inst >> 12));
}
// Extract function code 7 (bits 25-31)
inline fn funct7(inst: u32) u7 {
    return @as(u7, @truncate(inst >> 25));
}

inline fn sext(val: u32, comptime bits: u6) u32 {
    const shift: u5 = @intCast(32 - bits);
    return @as(u32, @bitCast(@as(i32, @bitCast(val << shift)) >> shift));
}

fn imm_i(inst: u32) u32 {
    // I-Type: [31:20] -> 12 bits
    const val = inst >> 20;
    return sext(val, 12);
}

fn imm_s(inst: u32) u32 {
    // S-Type: [31:25] | [11:7] -> 12 bits
    const val = ((inst >> 25) << 5) | ((inst >> 7) & 0x1F);
    return sext(val, 12);
}

fn imm_b(inst: u32) u32 {
    // B-Type: Scrambled. 12 bits of data + implicit 0.
    // Total range 13 bits.
    const bit_11 = (inst >> 7) & 1;
    const bits_4_1 = (inst >> 8) & 0xF;
    const bits_10_5 = (inst >> 25) & 0x3F;
    const bit_12 = (inst >> 31) & 1;

    const val = (bit_12 << 12) | (bit_11 << 11) | (bits_10_5 << 5) | (bits_4_1 << 1);
    return sext(val, 13);
}

fn imm_u(inst: u32) u32 {
    // U-Type: Upper 20 bits. No sign extension, just placement.
    return inst & 0xFFFFF000;
}

fn imm_j(inst: u32) u32 {
    // J-Type: Scrambled. 20 bits of data + implicit 0.
    // Total range 21 bits.
    const bits_19_12 = (inst >> 12) & 0xFF;
    const bit_11 = (inst >> 20) & 1;
    const bits_10_1 = (inst >> 21) & 0x3FF;
    const bit_20 = (inst >> 31) & 1;

    const val = (bit_20 << 20) | (bits_19_12 << 12) | (bit_11 << 11) | (bits_10_1 << 1);
    return sext(val, 21);
}

// --- 4. EXPORTED FUNCTIONS ---

export fn init_cpu(cpu: *CpuState) void {
    @memset(&cpu.regs, 0);
    @memset(&cpu.memory, 0);
    cpu.pc = 0;
    cpu.halted = false;
}

export fn run_cycles(cpu: *CpuState, cycles: u32) void {
    for (0..cycles) |_| {
        if (cpu.halted) break;
        step(cpu);
        cpu.regs[0] = 0; // x0 is hardwired to 0
    }
}
// --- 5. CORE EXECUTION LOGIC ---

fn step(cpu: *CpuState) void {
    // Fetch
    // Safety: Mask PC to memory size to prevent crash
    const pc_masked = cpu.pc & 0xFFFF;

    // Simplification: In real hardware we need to check alignment.
    // Here we construct a 32-bit int from 4 bytes (Little Endian).
    if (pc_masked + 4 > cpu.memory.len) {
        cpu.halted = true; // Stop if we run off memory
        return;
    }

    const b0 = @as(u32, cpu.memory[pc_masked]);
    const b1 = @as(u32, cpu.memory[pc_masked + 1]);
    const b2 = @as(u32, cpu.memory[pc_masked + 2]);
    const b3 = @as(u32, cpu.memory[pc_masked + 3]);
    const inst = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24);

    // Decode & Execute
    const op = opcode(inst);
    var next_pc = cpu.pc + 4; // Default behavior: advance 4 bytes

    switch (op) {
        // --- 1. ARITHMETIC WITH IMMEDIATE (ADDI, ANDI, etc) ---
        0x13 => {
            const dest = registerDestination(inst);
            const src = cpu.regs[registerSource1(inst)];
            const imm = imm_i(inst);

            switch (funct3(inst)) {
                0 => cpu.regs[dest] = src +% imm, // ADDI (+% is wrapping add)
                1 => cpu.regs[dest] = src << @as(u5, @truncate(imm)), // SLLI
                2 => cpu.regs[dest] = if (@as(i32, @bitCast(src)) < @as(i32, @bitCast(imm))) 1 else 0, // SLTI
                3 => cpu.regs[dest] = if (src < imm) 1 else 0, // SLTIU
                4 => cpu.regs[dest] = src ^ imm, // XORI
                5 => { // SRLI and SRAI share funct3=5
                    const shift_amount = @as(u5, @truncate(imm));
                    if ((imm >> 10) & 1 == 1) {
                        // SRAI (Arithmetic Shift - keeps sign)
                        cpu.regs[dest] = @as(u32, @bitCast(@as(i32, @bitCast(src)) >> shift_amount));
                    } else {
                        // SRLI (Logical Shift)
                        cpu.regs[dest] = src >> shift_amount;
                    }
                },
                6 => cpu.regs[dest] = src | imm, // ORI
                7 => cpu.regs[dest] = src & imm, // ANDI
            }
        },

        // --- 2. REGISTER-REGISTER ARITHMETIC (ADD, SUB, etc) ---
        0x33 => {
            const dest = registerDestination(inst);
            const val1 = cpu.regs[registerSource1(inst)];
            const val2 = cpu.regs[registerSource2(inst)];
            const f7 = funct7(inst);

            switch (funct3(inst)) {
                0 => {
                    if (f7 == 0) cpu.regs[dest] = val1 +% val2 // ADD
                    else cpu.regs[dest] = val1 -% val2; // SUB
                },
                1 => cpu.regs[dest] = val1 << @as(u5, @truncate(val2)), // SLL
                2 => cpu.regs[dest] = if (@as(i32, @bitCast(val1)) < @as(i32, @bitCast(val2))) 1 else 0, // SLT
                3 => cpu.regs[dest] = if (val1 < val2) 1 else 0, // SLTU
                4 => cpu.regs[dest] = val1 ^ val2, // XOR
                5 => {
                    const shift = @as(u5, @truncate(val2));
                    if (f7 == 0) cpu.regs[dest] = val1 >> shift // SRL
                    else cpu.regs[dest] = @as(u32, @bitCast(@as(i32, @bitCast(val1)) >> shift)); // SRA
                },
                6 => cpu.regs[dest] = val1 | val2, // OR
                7 => cpu.regs[dest] = val1 & val2, // AND
            }
        },

        // --- 3. LOAD (LW, LB, etc) ---
        0x03 => {
            const dest = registerDestination(inst);
            const addr = (cpu.regs[registerSource1(inst)] +% imm_i(inst)) & 0xFFFF; // Mask to RAM size

            switch (funct3(inst)) {
                0 => { // LB (Load Byte Signed)
                    const val = @as(i8, @bitCast(cpu.memory[addr]));
                    cpu.regs[dest] = @as(u32, @bitCast(@as(i32, val)));
                },
                1 => { // LH (Load Halfword Signed)
                    // Simplified: assuming little endian host
                    const v0 = cpu.memory[addr];
                    const v1 = cpu.memory[(addr + 1) & 0xFFFF];
                    const val = @as(i16, @bitCast(@as(u16, v0) | (@as(u16, v1) << 8)));
                    cpu.regs[dest] = @as(u32, @bitCast(@as(i32, val)));
                },
                2 => { // LW (Load Word)
                    const v0 = @as(u32, cpu.memory[addr]);
                    const v1 = @as(u32, cpu.memory[(addr + 1) & 0xFFFF]);
                    const v2 = @as(u32, cpu.memory[(addr + 2) & 0xFFFF]);
                    const v3 = @as(u32, cpu.memory[(addr + 3) & 0xFFFF]);
                    cpu.regs[dest] = v0 | (v1 << 8) | (v2 << 16) | (v3 << 24);
                },
                4 => { // LBU (Load Byte Unsigned)
                    cpu.regs[dest] = cpu.memory[addr];
                },
                5 => { // LHU (Load Halfword Unsigned)
                    const v0 = cpu.memory[addr];
                    const v1 = cpu.memory[(addr + 1) & 0xFFFF];
                    cpu.regs[dest] = @as(u32, v0) | (@as(u32, v1) << 8);
                },
                else => {},
            }
        },

        // --- 4. STORE (SW, SB) ---
        0x23 => {
            const addr = (cpu.regs[registerSource1(inst)] +% imm_s(inst)) & 0xFFFF;
            const val = cpu.regs[registerSource2(inst)];

            switch (funct3(inst)) {
                0 => cpu.memory[addr] = @as(u8, @truncate(val)), // SB
                1 => { // SH
                    cpu.memory[addr] = @as(u8, @truncate(val));
                    cpu.memory[(addr + 1) & 0xFFFF] = @as(u8, @truncate(val >> 8));
                },
                2 => { // SW
                    cpu.memory[addr] = @as(u8, @truncate(val));
                    cpu.memory[(addr + 1) & 0xFFFF] = @as(u8, @truncate(val >> 8));
                    cpu.memory[(addr + 2) & 0xFFFF] = @as(u8, @truncate(val >> 16));
                    cpu.memory[(addr + 3) & 0xFFFF] = @as(u8, @truncate(val >> 24));
                },
                else => {},
            }
        },

        // --- 5. BRANCHES (BEQ, BNE, etc) ---
        0x63 => {
            const val1 = cpu.regs[registerSource1(inst)];
            const val2 = cpu.regs[registerSource2(inst)];
            const imm = imm_b(inst);
            var take_branch = false;

            switch (funct3(inst)) {
                0 => take_branch = (val1 == val2), // BEQ
                1 => take_branch = (val1 != val2), // BNE
                4 => take_branch = (@as(i32, @bitCast(val1)) < @as(i32, @bitCast(val2))), // BLT
                5 => take_branch = (@as(i32, @bitCast(val1)) >= @as(i32, @bitCast(val2))), // BGE
                6 => take_branch = (val1 < val2), // BLTU
                7 => take_branch = (val1 >= val2), // BGEU
                else => {},
            }

            if (take_branch) {
                next_pc = cpu.pc +% imm;
            }
        },

        // --- 6. JUMP AND LINK (JAL) ---
        0x6F => {
            cpu.regs[registerDestination(inst)] = cpu.pc + 4;
            next_pc = cpu.pc +% imm_j(inst);
        },

        // --- 7. JUMP AND LINK REGISTER (JALR) ---
        0x67 => {
            const dest = registerDestination(inst);
            // JALR target is (rs1 + imm) with LSB masked to 0
            // Ensure target is evaluated *before* possibly overwriting rs1 
            const target = (cpu.regs[registerSource1(inst)] +% imm_i(inst)) & 0xFFFFFFFE;
            cpu.regs[dest] = cpu.pc + 4;
            next_pc = target;
        },

        // --- 8. SYSTEM (ECALL) ---
        0x73 => {
            const syscall_id = cpu.regs[17]; // a7
            const a0 = cpu.regs[10];
            const a1 = cpu.regs[11];
            const a2 = cpu.regs[12];

            switch (syscall_id) {
                // Syscall 0: HALT / EXIT
                0 => { 
                    cpu.halted = true; 
                },

                // Syscall 1: PRINT_INT (print the integer in a0)
                1 => {
                    std.debug.print("{d}\n", .{a0});
                },

                // Syscall 2: WRITE (write `a2` bytes from VM memory at address `a1` to stdout)
                2 => {
                    const start: usize = a1;
                    const len: usize = a2;
                    // Safety check to ensure VM doesn't read out of bounds
                    if (start + len <= cpu.memory.len) {
                        const Io = std.Io;
                        var threaded: Io.Threaded = .init_single_threaded;
                        const io = threaded.io();
                        
                        const slice = cpu.memory[start .. start + len];
                        
                        // writeStreamingAll takes a direct byte slice `[]const u8`
                        Io.File.stdout().writeStreamingAll(io, slice) catch |err| {
                            std.debug.print("VM IO Error: {any}\n", .{err});
                        };
                    }
                },

                // Syscall 3: OPEN FILE / READ FILE
                3 => {
                    const start: usize = a1;
                    const len: usize = a2;
                    // Safety check to ensure VM doesn't read out of bounds
                    if (start + len <= cpu.memory.len) {
                        const Io = std.Io;
                        var threaded: Io.Threaded = .init_single_threaded;
                        const io = threaded.io();
                        
                        // slice is const, but points to mutable memory ([]u8)
                        const slice = cpu.memory[start .. start + len];
                        
                        // readStreaming takes an array of slices `[]const []u8`
                        const iovecs = [_][]u8{slice};
                        if (Io.File.stdin().readStreaming(io, &iovecs)) |bytes_read| {
                            cpu.regs[10] = @as(u32, @intCast(bytes_read));
                        } else |err| {
                            std.debug.print("VM IO Error: {any}\n", .{err});
                            cpu.regs[10] = 0;
                        }
                    }
                },
                else => {
                    std.debug.print("Unhandled ecall: {d}\n", .{syscall_id});
                    cpu.halted = true;
                }
            }
        },

        // --- 9. UPPER IMMEDIATES ---
        0x37 => cpu.regs[registerDestination(inst)] = imm_u(inst), // LUI
        0x17 => cpu.regs[registerDestination(inst)] = cpu.pc +% imm_u(inst), // AUIPC

        else => {
            // Illegal instruction
            // cpu.halted = true;
        },
    }

    cpu.pc = next_pc;
}