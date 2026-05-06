
# Work-in-Progress Design Notes

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

---
### *Resolved Design Decisions*

* **Identifiers (Types vs. Namespaces vs. Functions):** [RESOLVED]. Identifiers are fundamentally namespaces/functions. The code natively supports this by treating `Type.Property` strictly as mangled functions. Types simply operate as constructors that yield views.
* **Macro Scope & Reality Rewriting:** [RESOLVED]. The `MacroRegistry` operates as a Stack. Block `{}` scopes dynamically push and pop language rules, allowing `std.langdef { ... }` or file-level `@using()` to dictate parsing without unpredictable global scope pollution.
* **Cross-File / Global Macro Injection:** [RESOLVED]. Resolved by capturing AST Block Scopes upon closing `}` and permanently attributing them to the top-level assigned identifier via 2-pass compilation. `@using(int)` now successfully intercepts the linear flow and alters the active language reality at exactly the intended moment.
* **Tail Recursion Optimization (TRO):** [RESOLVED]. Standard `jal` calls are bypassed dynamically at compile-time if the compiler matches a self-call, performing argument overwrite and `jal _loop` natively. Stack overflow risk in standard loops is mitigated.
* **Pattern Matching Dispatch:** [RESOLVED]. True runtime dynamic dispatch is now implemented. The compiler evaluates arguments and emits assembly branching (`bne`) to route execution to the correct mangled label block at runtime. Lack of exhaustive fallback patterns throws an explicit compile-time error if statically provable, or triggers a native runtime trap (`ecall`) if a dynamically evaluated value falls through all available patterns.