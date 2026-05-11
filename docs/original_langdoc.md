**Visible Mutation Guarantee**.
# Language Design Specification

## 1. Core Philosophy: Pragmatic Functional Systems Programming
This language is designed to bridge the gap between pure functional programming and bare-metal systems engineering (targeting RISC-V). 
* **No Garbage Collection:** Absolute control over memory.
* **Predictable Assembly:** Code maps cleanly to CPU instructions without hidden overhead.
* **Impure by Design, Pure by Default:** State mutation is allowed for systems-level performance, but strictly controlled and visible at the syntax level.
* **Axiomatic Grammar:** The entire language is built on a single, unified grammatical pattern.

## 2. The Universal Axiom
The language lacks traditional statements; it is entirely composed of declarations and expressions. Every major construct (functions, namespaces, macros) follows a single **Lambda / Pattern-Matching** syntax:
```text
binder : block_identifier = (bindings) : { body }
```
* **Functions:** `foo : res[int] = (x, y) : { res = x + y; }`
* **Namespaces/Types:** `int : self = (bytes[:4]) : { ... }` (Note: Namespaces are structurally mangled functions: `Type.Property`).
* **Macros:** `.@expr(10, a, +, b) : out = (a, b) : { ... }`

## 3. Lexical Memory & Macro Boundaries (The Rule of `{}`)
Both memory lifetimes and language syntax are strictly governed by lexical scopes. 
* **The `{}` Dictates the Stack:** A block `{` marks the stack pointer. A block `}` forces the stack pointer back to that mark. No temporary variables or expressions escape a block.
* **The `{}` Dictates Reality:** Macros (`.@expr`) modify the parser's rules. A macro defined inside a `{}` block pushes to the registry, completely altering the language syntax *only* within that block, and gracefully pops off reality when exiting `}`. 
* **Scope vs. Context:** 
  * *Scope (Runtime/Parse time):* Handles stack memory layout and Macro Registry parsing.
  * *Context (Compile-time):* Handles name mangling and identity (e.g., `int.max`). Context is inherited seamlessly by nested `{}` blocks unless explicitly redefined.

## 4. Initialization & Control Flow
* **Zero-Init by Default:** All declared variables are strictly Zero-Initialized by default, preventing undefined behavior.
* **Loops via Recursion & Runtime Dispatch:** The language does not have `if/else`, `while`, or `for` primitives. Control flow is achieved entirely through Native Pattern Matching. The compiler dynamically emits branching assembly to check values against function overloads at runtime.
* **Tail Recursion Optimization (TRO):** Loops are heavily enforced natively. A self-recursive call to the current function is intercepted by the compiler, overwriting local frame arguments and jumping directly to the start of the function body without pushing a new return address. This guarantees infinite loops do not overflow the stack.

## 4. Initialization & Control Flow
* **Zero-Init by Default:** All declared variables are strictly Zero-Initialized by default, preventing undefined behavior.
* **Dual-Nature Control Flow:** 
  * **Global Routing (Pattern Matching):** The language does not have built-in `while`, `for`, or `switch` primitives. Function-level control flow is achieved entirely through Native Pattern Matching. The compiler dynamically emits branching assembly (`bne`) to check values against function overloads at runtime.
  * **Local Branching (Inline Macros):** Local control flow (like `if` or `unless`) can be implemented as **Compile-Time Macros** that inject AST blocks directly into the caller's scope. Because they are expanded inline, they inject native assembly branches (`beq`/`bne`) and still adhere to local visibility of mutation.
* **Tail Recursion Optimization (TRO):** Loops are heavily enforced natively. A self-recursive call to the current function is intercepted by the compiler, overwriting local frame arguments and jumping directly to the start of the function body without pushing a new return address. This guarantees infinite loops do not overflow the stack.


## 5. Memory Interpretation: The `[view]` Lens & DOD
Because systems memory is raw bits, the `[ ]` operator acts as a **Lens** instructing the compiler how to interpret, slice, push, and pop data.
* **Sizing:** `x[int]` (Interpret as a segment)
* **Pointers:** `[ptr] = sum` (Write to the memory address held in `ptr`)
* **Data-Oriented Design (DOD):** There are no traditional OOP structs. Data lives in contiguous blocks, and Lenses combined with Splatting (`x, y, z = bytes`) extract, transform, and write back into those blocks using integer offsets.

## 6. The Visible Mutation Guarantee (VMG) & Locality
The language utilizes **Explicit Mutation**. Functions and expressions are conceptually pure transformations; they yield a result, and state is only updated when explicitly bound via `=`. 
* **Rule:** A macro (`.@expr`) is **Pure** unless its pattern explicitly contains the `=` symbol.
* **Pure Macros:** `(a, +, b)` cannot mutate `a` or `b`. If it contains an assembly instruction that writes to memory, or attempts to assign to a variable other than its own return value, the compiler throws a `Visible Mutation Guarantee Violation`.
* **Locality of Mutation (The Thunk Exemption):** AST Blocks (`{ ... }`) passed into macros at compile-time inherit the *caller's* purity context, not the macro's. Because macro blocks are expanded **inline** into the caller's stack frame, they are permitted to mutate local variables. Mutations are deemed safe because they remain hyper-local, share the parent's stack physics (`sp`), and do not hide state behind an opaque pointer.



## 7. The Module System
Every `.w` file acts as both an executable script and a library. 
* When passed to the compiler directly, the file executes top-to-bottom. 
* When `@import`ed or `@using`ed, the compiler manages its exported macros, definitions, and types, allowing safe unit testing per file. Block-scoped definitions keep imported libraries from globally polluting operator precedence rules.

## 8. comptime
* **Compile‑Time Pattern Dispatch** When multiple function patterns match a call, the compiler first tries to statically eliminate impossible candidates using literal arguments. If only one candidate remains, it is called directly with zero runtime overhead. If several remain, a runtime branch table is emitted.
Note: Full compile‑time evaluation of pure functions with comptime‑known arguments (like Zig’s comptime blocks) is a planned feature but not yet implemented.
* **Compile-Time Priority (Comptime Resolution)**: The compiler follows a strict resolution hierarchy:
 * Static Resolution: If expressions are purely constant (e.g., 1 + 2), they are evaluated during the compilation phase.
 * Generic/Inferred Propagation: If types are unspecified (e.g., raw literals), the compiler infers them based on usage patterns.
 * Dynamic Dispatch: If arguments are only available at runtime, the compiler emits a runtime branching table.
 * All logic is prioritized for comptime evaluation; only variables dependent on runtime memory state or IO are left to be handled via dynamic assembly dispatch.

## 9. First-Class Functions & The Ban on Closures
To support advanced Data-Oriented Design (DOD) transformations (like `map`, `filter`, and State Machines), functions can be passed as runtime values. However, to strictly protect the Visible Mutation Guarantee, **Closures are fundamentally banned.**
* **Pure Function Pointers:** A function passed as a value is strictly a physical memory address of a logic block. 
* **No Environment Capturing:** A runtime lambda or function value **cannot capture variables from its surrounding lexical scope**. If a function attempts to access a variable not explicitly passed as an argument, it triggers a compile-time error. 
* **Why?** Closures require hidden heap allocations (environment objects) and introduce silent, non-local state mutations. By enforcing strict purity on function values, the language guarantees that passing a function is as fast and predictable as a native RISC-V `jalr` instruction, with zero hidden side effects.

* **Note on Constant Folding:** Full compile-time evaluation of pure functions or constant algebraic expressions 
(e.g., evaluating `1 + 2` down to `3` natively without emitting ASM) 
is not yet fully implemented; those arithmetic operations are compiled into instructions unless strictly parsed as solitary literal tokens.
this will be done by the vm itself during compilation via micro binaries to avoid code duplication.
