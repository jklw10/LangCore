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
* **Namespaces/Types:** `int : self = (bytes[:4]) : { ... }`
* **Macros:** `.@expr(10, a, +, b) : out = (a, b) : { ... }`

## 3. Lexical Memory Boundaries (The Rule of `{}`)
Memory lifetimes are strictly governed by lexical scopes. 
* **The `{}` Dictates the Stack:** A block `{` marks the stack pointer. A block `}` forces the stack pointer back to that mark.
* **No Escaping:** Any temporary variable or expression pushed to the stack inside `{}` is forcefully popped and destroyed at `}`.
* **Scope vs. Context:** 
  * *Scope (Runtime):* Handles stack memory layout (created by every `{}`).
  * *Context (Compile-time):* Handles name mangling and identity (e.g., `int.max`). Context is inherited seamlessly by nested `{}` blocks unless explicitly redefined.

## 4. Initialization & Control Flow
* **Zero-Init by Default:** All declared variables are strictly Zero-Initialized by default, preventing undefined behavior.
* **Loops via Recursion:** The language does not have `while` or `for` loops. Control flow is achieved entirely through Recursive Pattern Matching.
* **TRO vs TCO:** 
  * *Release Builds:* Utilize Tail Call Optimization (TCO) universally.
  * *Debug Builds:* Utilize Tail Recursion Optimization (TRO). Standard A-to-B function calls retain their stack frames, guaranteeing perfect stack traces, while self-recursion is optimized into standard assembly loops to prevent stack overflows.

## 5. Memory Interpretation: The `[view]` Lens & DOD
Because systems memory is raw bits, the `[ ]` operator acts as a **Lens** instructing the compiler how to interpret, slice, push, and pop data.
* **Sizing:** `x[int]` (Interpret as a 4-byte segment)
* **Pointers:** `[ptr] = sum` (Write to the memory address held in `ptr`)
* **Data-Oriented Design (DOD):** There are no traditional OOP structs. Data lives in contiguous blocks, and Lenses combined with Splatting (`x, y, z = bytes`) extract, transform, and write back into those blocks using integer offsets.

## 6. The Visible Mutation Guarantee (VMG)
The language utilizes **Explicit Mutation**. Functions and expressions are conceptually pure transformations; they yield a result, and state is only updated when explicitly bound via `=`. 
* **Rule:** A macro (`.@expr`) is **Pure** unless its pattern explicitly contains the `=` symbol.
* **Pure Macros:** `(a, +, b)` cannot mutate `a` or `b`. If it contains an assembly instruction that writes to memory, or attempts to assign to a variable other than its own return value, the compiler throws a `Visible Mutation Guarantee Violation`.
* **Mutating Macros:** `(a, =, b)` or `(a, +, =, b)` contain `=`. The compiler grants these macros mutation rights. When reading code, any memory mutation is structurally guaranteed to have a visible `=` sign on that line.

## 7. The Module System
Every `.w` file acts as both an executable script and a library. 
* When passed to the compiler directly, the file executes top-to-bottom. 
* When `@import`ed, the compiler extracts its namespaces, types, and definitions, but gracefully ignores any naked execution statements. This allows every file to act as its own unit test suite.


current phase is to make the basics work in just the debug build