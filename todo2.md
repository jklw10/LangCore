
# Work-in-Progress Design Notes

the file's a mess, mostly for just noting down discussion points.

This file tracks active language design questions, planned features, and philosophical tradeoffs that require further definition before hardcoding into the compiler.

### 1. Zero-Initialization via Type Constructors (Priority 1)
**Feature:** Transitioning the strict 0-byte pushing to a smart function call.
**Current State:** A variable declared like `x[int];` currently hard-pushes the `x0` assembly register to the stack to ensure zero-init.
**Planned Solution:** This will be changed soon so the compiler structurally evaluates it as an AST Call: `int(0)`. If a type requires multiple 0's or custom initialization, passing `0` to the type function provides extreme flexibility natively.

### 2. Splatting / Tuple Destructuring (Priority 2)
**Feature:** Extracting data natively via integer offsets: `x, y, z = bytes`.
**Decision:** Deferred. Because the language heavily supports macros and manual memory slicing (`[ptr + 4]`), tuple destructuring can either be built as a standard library macro or deferred to a Phase 2 native compiler feature.

### 3. 8-bit Alignment Conversion
**Feature:** Detach the `x[int]` logic from the compiler's hardcoded 4-byte `REGISTER_SIZE` steps, allowing true byte-level addressing on the stack to accurately model small systems.

### 4. Standard Library & Syntax Sugar (Phase 2)
**Feature:** Building out the core language ergonomics natively or via macros.
* **Types:** Standardize `int`, `bool`, `float`, etc., as globally accessible constructor functions.
* **Slicing Sugar:** Transform `a[:4]` natively to `a[0:4]`.
* **Implicit Calls:** Allow the invocation of a function without parentheses if the context uniquely identifies it, or provide a default fallback (`i` evaluates to `i()` if unbound as a value but exists as a function).
* **Implicit Assignment / Return Propagation:** In pattern matching or functions, assigning a variable to itself (e.g., `sum = sum;`) or returning the unchanged state should be implicitly handled.
* **Easy Loops:** Provide a standard macro for simple bounded loops to abstract away the manual recursive pattern matching boilerplate.


## 5. Memory, Allocation, and Views
*   **Pointer Sizing (`[ptr]`):** By default, memory is evaluated at the physical hardware minimum. If a blind pointer dereference is assigned (`[ptr] = 0`), it defaults strictly to a **1-byte view** (the `byte` type). To write larger contiguous blocks, the pointer explicitly requires a lens: `[ptr][int] = 0` tells the compiler to emit a 4-byte write.
*   **Void-to-Value Allocation:** Variables do not inherently possess a type until initialized via a constructor. 
    *   An undeclared variable `x` begins as `void`.
    *   The assignment `x = int(5)` triggers physical stack allocation (Void -> Value). 
    *   Writing `x = 5` is strictly syntax sugar for `x = int(5)`. The `x[int]` syntax is reserved structurally for input bindings (function parameters or macro holes).

eventually microbinaries for comptime.


## 6. Relational Precedence & Macro Overloading
Hardcoded integer precedence (e.g., binding power `10` for `+`) is phased out in favor of **Relational Precedence via Named Macros**. 
*   Operators dictate their binding power relative to other known operators/macros (e.g., `before *` or `after ==`). 
*   **Macro Pattern Matching:** Because macros are now strictly named and relationally anchored, they support the exact same pattern-matching dispatch as standard functions. You can overload a macro by defining multiple patterns under the same identifier; the compiler will match the correct structural expansion at compile time based on the passed AST nodes.
something int the shape of .@expr(add,a,*,b)mul


## 7. Comptime Traps via vm
When the dynamic dispatch system encounters arguments that fail all patterns, it emits a hardware `ecall` trap. 
*   To prevent the compiler from emitting a binary that immediately crashes at runtime when arguments are statically known, Phase 2 will introduce a **vm Micro-Binary evaluation step**. 
*   During compilation, if the AST evaluates a known path that hits a trap, the internal VM will catch the `ecall` natively and immediately throw a hard Compile-Time Error, guaranteeing the binary is never written.

---
### *Resolved Design Decisions*

* **Identifiers (Types vs. Namespaces vs. Functions):** [RESOLVED]. Identifiers are fundamentally namespaces/functions. The code natively supports this by treating `Type.Property` strictly as mangled functions. Types simply operate as constructors that yield views.
* **Macro Scope & Reality Rewriting:** [RESOLVED]. The `MacroRegistry` operates as a Stack. Block `{}` scopes dynamically push and pop language rules, allowing `std.langdef { ... }` or file-level `@using()` to dictate parsing without unpredictable global scope pollution.
* **Cross-File / Global Macro Injection:** [RESOLVED]. Resolved by capturing AST Block Scopes upon closing `}` and permanently attributing them to the top-level assigned identifier via 2-pass compilation. `@using(int)` now successfully intercepts the linear flow and alters the active language reality at exactly the intended moment.
* **Tail Recursion Optimization (TRO):** [RESOLVED]. Standard `jal` calls are bypassed dynamically at compile-time if the compiler matches a self-call, performing argument overwrite and `jal _loop` natively. Stack overflow risk in standard loops is mitigated.
* **Pattern Matching Dispatch:** [RESOLVED]. True runtime dynamic dispatch is now implemented. The compiler evaluates arguments and emits assembly branching (`bne`) to route execution to the correct mangled label block at runtime. Lack of exhaustive fallback patterns throws an explicit compile-time error if statically provable, or triggers a native runtime trap (`ecall`) if a dynamically evaluated value falls through all available patterns.


i think i should just change platform to have a scope start and scope end, have the assert for scope size in there, and since the language shape is what it is, it should be possible to make the caller / call position responsible for pushing the return value positions onto the stack. especially due to named return being the only way. so you always know how much is being returned before even calling the function. so i can make the entire internals of a function a 0 sum for stack.
i can guarantee that stack size only increases when a symbol is being declared the first time?
oh it's like rust's lifetimes and ownership but easy understand?
hmm and i can just completely delete everything within scope when exiting. heap touches would pass through [ptr] out too.