# Compiler Architecture & Design Decisions

This document outlines the structural framework underpinning the compiler. It serves as a blueprint for implementing the compiler natively, independent of any host language constraints.

## 1. Multi-Pass Architecture
The compiler avoids single-pass compilation to support global macro resolution and forward declarations. It operates via the `Workspace`:

1.  **File Discovery & Signature Extraction:** Parses the entry file and `@import` dependencies into skeletal ASTs. Extracts function signatures and type namespaces.
2.  **Semantic Parsing:** Re-parses the files using fully populated type and macro environments. Recursively inlines imported ASTs.
3.  **Function Registration & Mangling:** Walks the full AST to identify function definitions. Mangles labels based on argument patterns (e.g., `func_val1_any0`) and stores them in a registry.
4.  **Code Generation:** Sequentially walks execution blocks, allocating stack frames, expanding macros, and emitting machine instructions.

## 2. Memory & Stack Physics
The compiler strictly models hardware realities. There is no heap, no garbage collection, and no hidden allocations.

*   **Strict Depth Tracking:** The compiler statically tracks the stack pointer byte depth via `current_stack_depth` within local scopes to ensure absolute cleanup upon scope exit.
*   **The Frame Pointer (`fp`):** Function boundaries establish a strict Frame Pointer. Arguments passed into the function physically live *below* the `fp` (accessed via negative offsets like `-3(fp)`), while local variables declared within the function's scope are allocated *above* the `fp` (accessed via positive offsets like `+1(fp)`).
*   **Zero-Initialization:** Declared variables physically force `x0` (zero) onto the stack.
*   **Frame Boundaries:** Scopes mathematically record stack depth upon entry. Upon exit, the compiler mathematically shrinks the stack pointer (`sp`) back to the baseline.
*   **Static Embeds:** Strings and `@embed` files are statically packed into the text segment via a physical jump-over sequence, bypassing the dynamic stack.

## 3. Dynamic Pattern Dispatch
Control flow defers entirely to Native Pattern Matching.

*   **Runtime Branching:** Functions are compiled into distinct assembly blocks. When a function is called, the compiler checks the registry and emits inline assembly sequences (`bne`) to evaluate pushed arguments against literal patterns.
*   **Fall-through Traps:** If an argument fails all pattern checks, execution falls through to `halt()` (an `ecall` trap).

## 4. Tail Recursion Optimization (TRO)
Loops are implemented via recursion, and the compiler natively intercepts infinite stack growth.

*   **Detection:** During a `Call`, if the target function name matches the currently executing function, and the return assignment structure perfectly matches the caller's, it flags a Tail Recursive loop.
*   **Argument Overwrite:** The compiler pops the evaluated arguments into temporary execution registers (`tco` pool), aggressively overwrites the current caller's parameter offsets, and natively jumps to the function's internal loop label, avoiding pushing a new return address.

## 5. Macro Expansion & The Caller Context
Macros utilize the *caller's* stack frame and local variables inline. When a macro captures arguments, they are wrapped in `CallerContext` nodes. The code generator responds to this by temporarily restoring the compiler's tracking of `pure_context_out_var` to its state when the macro was triggered, preventing offset and mutation corruption.

## 6. The Visible Mutation Guarantee (VMG)
The compiler enforces state purity at the architectural level.

*   **Purity Contexts:** Pure macro calls lock an internal `pure_context_out_var`. 
*   **Strict Asserts:** If the AST attempts to emit a mutating assembly instruction (like `store` or `sw`) targeting a variable *other* than the locked out-variable, or attempts a blind pointer dereference (`Lens` assignment), the compiler immediately structurally faults.

## 7. Splatting, Slicing, and DOD Pipelines
Data tuples and arrays are intrinsically flat blocks of memory on the stack.

*   **Destructuring (`Tuple`):** When assigning to a tuple `a, b = x`, the compiler pops the data sequentially into safe hardware registers and writes them to the individual target variable offsets.
*   **Lenses (`[ptr]` and `[0:4]`):** Lenses act as data pluckers. For pointer dereferencing, they evaluate raw integer addresses to push/pop memory. For slicing, they mathematically recalculate offsets from the bottom of the pushed block, read only the requested register limits, and obliterate the remainder of the flat sequence.