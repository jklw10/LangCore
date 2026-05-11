# Assembler Architecture & Binary Emission

This document outlines the design decisions and physical constraints of the Assembler module. As the lowest level of the compilation pipeline, the Assembler acts as the final translator, converting abstract hardware instructions (like `add`, `sw`, `bne`) into raw, executable machine code. 

## 1. The Role of the Assembler
While the Platform layer dictates *which* instructions to use to achieve a semantic goal, the Assembler dictates *how* those instructions are physically encoded into memory. It is entirely ignorant of the language's semantics, types, or syntax.
*   **1:1 Hardware Mapping:** The assembler provides a strict, one-to-one mapping to the target architecture's Instruction Set Architecture (ISA). It does not synthesize instructions (like breaking up large integers); that is the Platform's job.
*   **Direct Binary Emission:** It does not produce intermediate assembly text. It packs opcodes, register IDs, and immediates directly into a contiguous binary byte buffer.

## 2. Bit-Level Instruction Synthesis
The assembler structurally adheres to the hardware's physical decoding logic. For RISC-V, this means strictly grouping instructions into standard encoding formats (R, I, S, B, and J types).
*   **Bitwise Packing:** Instructions are built using strict bitwise shifting and masking. The assembler takes raw integer arguments (e.g., `rs1`, `rs2`, `rd`, `funct3`, `opcode`) and shifts them into their exact hardware-specified bit indices to form a single 32-bit (4-byte) instruction.
*   **Immediate Scrambling:** To optimize physical hardware multiplexers, modern architectures (like RISC-V) scramble the bits of immediate values in Branch (B-type) and Jump (J-type) instructions. The assembler completely encapsulates this complex bit-shuffling, exposing a clean API that simply accepts a standard integer offset.

## 3. Single-Pass Emission & Backpatching (Fixups)
To maximize compilation speed and eliminate the need for a complex Linker or intermediate two-pass architecture, the assembler emits code linearly using a **Backpatching** strategy.

*   **The Forward-Reference Problem:** The compiler frequently needs to jump forward to a label that has not yet been compiled (e.g., jumping over an `if` block's body). The assembler cannot know the physical offset distance at the time the jump instruction is requested.
*   **The Fixup Registry:** When the assembler encounters a forward reference, it does not halt or fail. Instead, it:
    1.  Records the exact byte offset (Program Counter) where the jump instruction is being emitted.
    2.  Adds this location to a `Fixup Registry` under the requested label's name.
    3.  Emits a dummy instruction (with a `0` offset) into the binary buffer to hold the space.
*   **Label Resolution:** When the compiler finally declares the target label, the assembler checks the registry. If previous jumps were waiting for this label, the assembler calculates the now-known physical distance (Offset = Current PC - Jump PC), encodes the offset, and reaches back into the binary buffer to overwrite the dummy instructions with the correct binary jumps.

## 4. PC-Relative Addressing
The assembler automatically manages physical program flow. It understands that target architectures handle branching via PC-Relative offsets (jumping *X bytes forward* or *Y bytes backward* from the current instruction). 
*   When a label is passed to a branching instruction, the assembler calculates the strict delta between the current Program Counter and the target label's Program Counter. The compiler never has to manually calculate byte distances.

## 5. Finalization & Executable Integrity
The assembler acts as the final gatekeeper for execution safety. 
*   **Dangling References Verification:** Before the executable binary is sealed and handed to the CPU or output to a file, the assembler performs a strict structural check on the Fixup Registry. 
*   If any labels remain unresolved (i.e., a jump was requested to a label that was never defined), the assembler throws a fatal error, guaranteeing that no undefined behavior or wild jumps can exist in the compiled binary.