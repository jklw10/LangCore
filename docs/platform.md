# Platform & Hardware Abstraction Layer (HAL)

This document outlines the architectural design and responsibilities of the Platform module. The Platform serves as the Hardware Abstraction Layer (HAL) between the compiler's logical code generation and the raw physical hardware (currently RISC-V). 

By isolating hardware-specific knowledge, the compiler remains fundamentally retargetable.

## 1. The Role of the Platform Layer
The core compiler (`compiler.w`) operates on abstract concepts: allocating bytes, shrinking scopes, tracking purity, and jumping to labels. It should never hardcode an instruction like `addi x2, x2, 4`. 

Instead, the Platform translates semantic compiler requests into target-specific opcodes and memory mechanics. It encapsulates:
*   **Target Architecture Specifics:** Word sizes, alignment, and physical memory start addresses (e.g., `stack_start = 0x8000`).
*   **Hardware Interface (Backend API):** Exposes high-level physical operations to the compiler, such as `push()`, `pop()`, `call()`, `read_local()`, and `shrink_stack()`.

## 2. Abstract Stack Physics
Because the language lacks a heap and garbage collector, the stack is the sole source of memory layout. The Platform explicitly models how the target hardware's stack operates.
*   **Stack Pointer (SP) Governance:** Maps the abstract concept of a stack pointer to a physical hardware register (e.g., register `2` / `x2`).
*   **Increment/Decrement Mechanics:** Defines the byte-size of a standard register (`REGISTER_SIZE = 4`) and enforces physical stack growth directions via standard `push()` and `pop()` abstractions.
*   **Direct Local Offsets:** Allows the compiler to manipulate data relative to the active stack pointer via `read_local` and `write_local`, enabling the compiler's zero-cost negative-offset variable tracking.

## 3. Register Allocation & ABI Abstractions
The Platform governs the physical registers of the CPU, categorizing them for the compiler to use safely without clashing with hardware limitations.
*   **Register Mapping:** Translates human-readable ABI names (`ra`, `sp`, `a0`, `t0`) into their physical integer counterparts for the assembler.
*   **Execution Temporaries:** Provides dedicated pools of temporary registers specifically reserved for isolated operations:
    *   `get_temp_regs_for_asm()`: Transient registers used for shuttling data during standard math/logic instructions.
    *   `get_temp_regs_for_tco()`: A wider pool of registers used specifically during Tail Call Optimization (TRO) to hold evaluated arguments safely while the caller's stack frame is aggressively overwritten.
*   **Safe Registers:** Identifies callee-saved registers that can be relied upon across complex control-flow jumps.

## 4. Hardware Limitations & Synthesized Operations
Physical CPUs have limitations that the high-level language should not care about. The Platform acts as a synthesizer to bridge these gaps seamlessly.
*   **Immediate Synthesis (`load_immediate`):** In RISC-V, a 32-bit CPU cannot load a 32-bit constant into a register in a single instruction because instructions themselves are only 32 bits long. The Platform automatically detects when a value exceeds the 12-bit immediate limit (`-2048` to `2047`) and synthesizes a dual-instruction sequence (`lui` + `addi`) without the compiler's awareness.
*   **Memory Swizzling:** Provides composite functions like `push_mem` and `pop_mem` to handle the multi-step process of loading an address, dereferencing it, and pushing its value to the stack.

## 5. Instruction Semantics & VMG Enforcement
The Platform is not just a passive instruction emitter; it actively categorizes instructions so the compiler can enforce language guarantees (like the Visible Mutation Guarantee).
*   **Volatility & Purity (`no_rd_instructions`):** The Platform knows which instructions structurally do not have a destination register (`rd`). Instructions like `store`, `sb`, or `bne` operate via side effects (modifying memory or program counters). 
*   **Mutation Flagging:** By exposing `is_mutating_instruction()`, the Platform allows the AST and Code Generator to structurally block inline assembly that attempts to secretly mutate state inside a pure macro block.
*   **Branch Identification:** Identifies which arguments in which instructions represent jump targets (labels), ensuring the assembler knows when to trigger label resolution/fixups instead of expecting literal integer offsets.