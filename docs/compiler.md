# Compiler Architecture & Design Decisions

This document outlines the structural framework and design philosophies underpinning the compiler. It serves as a blueprint for implementing the compiler natively, independent of any host language constraints.

## 1. Multi-Pass Architecture
The compiler avoids single-pass compilation to support global macro resolution, forward declarations, and out-of-order execution flows without relying on a linker. It operates in four distinct phases:

1.  **File Discovery & Signature Extraction:** Parses the entry file and any `@import` dependencies into skeletal Abstract Syntax Trees (ASTs). It extracts function signatures, parameter counts, and type namespaces to build a global symbol map.
2.  **Semantic Parsing:** Re-parses the files using the fully populated type and macro environments. It recursively inlines imported ASTs into the main program tree to ensure global macros are active before code generation begins.
3.  **Function Registration & Mangling:** Walks the full AST to identify function definitions. It mangles labels based on argument patterns (e.g., separating literal values from generic `any` identifiers) and stores them in a registry for dynamic dispatch.
4.  **Code Generation:** Sequentially walks the execution blocks, allocating stack frames, expanding macros, and emitting raw machine instructions.

## 2. Memory & Stack Physics
The compiler strictly models hardware realities. There is no heap, no garbage collection, and no hidden allocations.

*   **Strict Depth Tracking:** The compiler statically tracks the stack pointer (`sp`) byte depth at every AST node. 
*   **Negative Offset Mapping:** Variables physically live in the active frame *below* the current floating `sp`. Accessing a variable evaluates its absolute stack position and subtracts the current depth to generate a strict negative offset (e.g., `-12(sp)`).
*   **Zero-Initialization:** All declared variables physically force `x0` (zero) onto the stack to ensure deterministic hardware states.
*   **Frame Boundaries:** Scopes (defined by `{}`) strictly record the stack depth upon entry. Upon exit, the compiler mathematically guarantees the depth returns to the entry baseline, automatically emitting stack-shrink instructions to discard scoped variables.

## 3. Dynamic Pattern Dispatch
The language lacks native `if/else`, `while`, or `for` loops, deferring all control flow to Native Pattern Matching.

*   **Mangled Labels:** Functions are compiled into distinct assembly blocks named via their patterns (e.g., `func_val1_any0`).
*   **Runtime Branching:** When a function is called, the compiler checks the statically compiled registry. It emits inline assembly sequences (`bne` - branch-not-equal) to evaluate the pushed arguments against the literal patterns.
*   **Fall-through Traps:** If an argument fails all pattern checks at runtime, the execution falls through to an `ecall` trap, intentionally crashing the system to prevent undefined behavior.

## 4. Tail Recursion Optimization (TRO)
Because loops are implemented via recursion, the compiler natively intercepts infinite stack growth.

*   **Detection:** During a function call, if the target function name matches the currently executing function, and the return targets match the caller's assignment structure, the compiler flags the operation as a Tail Recursive loop.
*   **Argument Overwrite:** Instead of pushing a new Return Address (`ra`) and executing a standard Jump-and-Link (`jal`), the compiler pops the newly evaluated arguments into temporary execution registers, physically rewrites them into the current caller's parameter offsets, and emits a standard jump to the function's internal loop label.

## 5. Macro Expansion & The Caller Context
Macros manipulate the AST inline at compile time. 

*   **Inline Physics:** Because macros expand directly into the caller's AST, they utilize the *caller's* stack frame and local variables. 
*   **Caller Context Nodes:** When a macro captures arguments, they are wrapped in special `CallerContext` nodes. This ensures that when the macro's body is evaluated, the captured arguments are compiled strictly against the hardware stack state present *before* the macro began executing, preventing offset corruption.

## 6. The Visible Mutation Guarantee (VMG)
The compiler enforces state purity at the architectural level.

*   **Purity Contexts:** Macros without the explicit `=` mutation token are marked pure. 
*   **Strict Asserts:** If the code generator enters a pure context, it locks an internal "out variable". If any subsequent AST node attempts to emit a mutating assembly instruction (like `store` or `sw`) targeting a variable other than the locked out-variable, the compiler immediately faults.
*   **Deref Blocking:** Blind pointer dereferencing (`[ptr] = x`) is structurally blocked inside pure contexts, as it represents a mutation to an unknown memory address that cannot be verified statically.


## 7. Splatting and Data-Oriented Pipelines
Data tuples and arrays are inherently flat. 

*   **(TODO) Destructuring (`Tuple`):** When assigning to a tuple `a, b = x`, the compiler ensures the right-hand stack depth perfectly matches the left-hand request size. It pops the data into sequential safe hardware registers and sequentially writes them to the target variable offsets (or pointer targets).