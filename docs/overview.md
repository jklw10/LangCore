# Language Overview & Core Philosophy

This language is designed to bridge the gap between pure functional programming and bare-metal systems engineering. It provides the composability and bottom-up construction of languages like Lisp or Clojure, but strictly enforces the physical realities of hardware execution (targeting RISC-V).

There is no runtime, no garbage collector, and no hidden allocation. The language is built on a small set of absolute physical rules, trading traditional syntactic sugar for ultimate predictability and control.

---

## 1. Core Tenets

*   **Zero-Cost Predictability:** Code maps cleanly to CPU instructions. If memory is allocated or a jump occurs, it is explicitly visible in the structure of the code.
*   **Impure by Design, Pure by Default:** State mutation is required for system-level performance, but it is strictly controlled, structurally isolated, and visibly guaranteed at the syntax level.
*   **Axiomatic Grammar:** There are no disparate statements or traditional keywords (`if`, `while`, `struct`, `class`). The entire language is built upon a single grammatical pattern.

this is a complete hallucination, but it does bring an interesting thought, what would a language with this as a tenet look like?
*   **Negative Space Programming:** Code correctness is proven by mapping the negative space—asserting what data *cannot* be. Assertions are mandatory for state boundaries, acting simultaneously as compiler hints, physical memory constraints, and documentation.

---

## 2. The Universal Axiom
Every major construct in the language (functions, namespaces, macros, types) is structurally identical. They all follow a single **Lambda / Pattern-Matching** syntax:

```rs
binder : named_returns = (bindings) : { body }
```

*   **Functions:** `foo : res[int] = (x, y) : { res = x + y; }`
*   **Types & Namespaces:** `int : self = (bytes[:4]) : { ... }` *(Namespaces are structurally mangled functions: `Type.Property`)*.
*   **Dynamic Dispatch:** `foo : res[int] = (1, y) : { res = y; }` *(Matches only when the first argument is exactly 1)*.
*   **Macros:** `.@expr(2, if, cond, t_body) : out = (cond[bool], t_body) : { ... }`

---

## 3. The Rule of `{}` (Lexical Physics)
Both memory lifetimes and language syntax are strictly governed by lexical scopes. The `{}` braces act as physical hardware boundaries.

*   **The `{}` Dictates the Stack:** A `{` block marks the current hardware stack pointer. All variables declared within push the stack forward. The closing `}` mathematically forces the stack pointer back to that exact mark, instantly destroying local state without GC overhead.
*   **The `{}` Dictates Context:** Macros alter the parser's rules. A macro defined inside a `{}` block pushes to the compiler's Macro Registry, completely altering the language's syntax *only* within that block, gracefully reverting context upon exiting `}`.

---

## 4. Control Flow & Native Pattern Matching
The language contains **no built-in control flow keywords**. Control flow is achieved through two mechanisms:

1.  **Global Routing (Dynamic Dispatch):** Instead of `switch` or `else if` chains, functions are overloaded with literal patterns. The compiler dynamically emits branching assembly (`bne`) to check values against function overloads at runtime. If all patterns fail, the system intentionally traps (`ecall`) to prevent undefined behavior.
2.  **Local Branching (Macros):** Constructs like `if` are implemented in the standard library as macros that inject raw branching assembly (`beq`) and inline AST blocks directly into the caller's scope.

### Tail Recursion Optimization (TRO)
Loops (`while`, `for`) do not exist. Repetition is enforced natively via self-recursion. 
When the compiler detects a function calling itself, it structurally intercepts the call. Instead of pushing a new return address and blowing up the stack, it pops the evaluated arguments, rewrites the current local frame, and jumps natively to the start of the function body. **Infinite loops are guaranteed safe and cost-free.**

---

## 5. Memory & Data-Oriented Design (DOD)
Data lives in raw, contiguous memory blocks. There are no opaque objects or hidden heap pointers.

*   **Zero-Initialization:** All declared variables physically force zero bytes (`x0`) onto the stack by default to prevent undefined hardware states. (Custom initialization is handled via Type Constructors like `int(0)`).
*   **The `[view]` Lens:** Because memory is just raw bits, types are merely "Lenses" that instruct the compiler how to interpret, slice, or offset data. 
*   **Raw Pointers:** Variables can hold raw integer addresses (`ptr = 65000`). Dereferencing is done via explicit explicit assignment to a bracketed pointer: `[ptr] = sum;` writes the value of `sum` directly to physical memory.
*   **Splatting / Destructuring:** Data arrays and tuples are flat. Destructuring extracts data natively via sequential hardware registers: `x, y, z = bytes`.

---

## 6. The Visible Mutation Guarantee (VMG)
The language utilizes **Explicit Mutation**. Functions and expressions are pure transformations; they yield a result, and state is only updated when explicitly bound via `=`.

*   **Pure Macros:** If a macro's signature does not contain the `=` symbol, it is strictly pure. If it attempts to emit assembly that mutates memory (`store`), or blind-dereferences a pointer, the compiler throws a structural fault.
*   **Locality of Mutation (The Thunk Exemption):** AST Blocks (`{ ... }`) passed into macros at compile-time inherit the *caller's* purity context, not the macro's. Because macro blocks are expanded **inline** into the caller's stack frame, they are permitted to safely mutate the caller's local variables without opaque side-effects.

---

## 7. Functions & The Ban on Closures
To support advanced DOD transformations, functions are architecturally treated as pure logic blocks. However, to strictly protect the Visible Mutation Guarantee, **Closures are fundamentally banned.**
*   **Functions as value** **TODO**: passed by pointer to logic location. I think with the rules in place this might be doable statically at compile time?
*   **No Environment Capturing:** A runtime lambda cannot capture variables from its surrounding lexical scope. If a function requires external data, it must be explicitly passed as an argument.
*   **Function Pointers (Planned):** While the syntax allows passing functions as values, true dynamic dispatch over raw memory addresses is heavily restricted to prevent opaque side-effects. Currently, function resolution is strictly evaluated at compile-time via the static registry.

---

## 8. Comptime & Module System
The compiler prioritizes evaluating logic at compile time before emitting raw assembly.

*   **Comptime Resolution Hierarchy:** 
    1.  *Static:* Purely constant expressions (`1 + 2`) are evaluated and folded during compilation.
    2.  *Generic Propagation:* Unspecified types (raw literals) are inferred based on usage pipelines.
    3.  *Dynamic:* Only state dependent on IO or runtime memory falls back to dynamic assembly branching.
*   **Modules:** Every `.w` file acts as both an executable script and a library. Files imported via `@import` and `@using` allow safe, block-scoped macro injection, keeping imported libraries from globally polluting the host file's operator precedence.

## 9. The Physical Meaning of `.` (Static vs. Stack)
The language eliminates the Object-Oriented ghost of "instances." Because there is no hidden heap and no opaque objects, a type is merely a *Lens*—a pure function that slices the stack. 

The `.` prefix serves a strict, physical hardware purpose: **It dictates whether an operation targets the dynamic stack or the static binary segment.**

*   **No Dot (Stack / Execution Flow):** Dotless identifiers represent dynamic stack manipulation or global execution flow.
    *   `value = bytes`: "Map this local stack data to the return slot."
    *   `div_rem : ...`: "Emit this function block into the context as a standard label."
*   **With Dot (Static / Namespace Registry):** The `.` prefix explicitly tells the compiler: *"Bypass the dynamic stack and anchor this construct statically to the `{}` namespace I am currently inside."*
    *   `.str = "hello"`: Emits bytes directly into the static `.rodata` segment.
    *   `.max = 0x7fff`: Binds a constant to the namespace's static dictionary (`int.max`).
    *   `.rand : ...`: Emits a function block, legally binding its label to the namespace (`int.rand`).
    *   `.@expr`: Emits a macro directly into the compiler's static Macro Registry.

## 10. Namespace Hygiene and Explicit Imports
The language enforces strict namespace hygiene to prevent accidental global pollution. 

Dotless functions (like `div_rem`) defined inside a file or module are not "private" in the traditional OOP sense—they are simply untethered to a specific type lens. However, **implicit importing is banned.** 
If File A defines a dotless `div_rem`, File B cannot accidentally execute it just by importing File A. File B must explicitly invoke `@using(File A)` to pull those untethered symbols into its active routing scope, ensuring that operator precedence and global functions are never polluted by accident.