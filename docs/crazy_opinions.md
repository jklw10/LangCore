
## 1. The "No Strings" Philosophy
The language physically lacks a `STRING` token in its lexer taxonomy. 
*   **Design Stance:** Strings are an abstraction of contiguous memory arrays. Hardcoding text into a systems binary is an anti-pattern for this language's goals. 
*   **Resolution:** "Read files." Text or character data must be loaded into memory via I/O syscalls at runtime or ingested as raw bytes. The compiler will not parse `"Hello World"`.

## 2. Macro Hygiene & Compiler Safeguards (or Lack Thereof)
*   **Hygiene via Mangling:** To prevent variables defined inside an inline macro from corrupting identically named variables in the caller's stack frame, the AST automatically mangles macro-internal identifiers.
*   **Infinite Comptime Loops:** There is no hardcoded recursion limit in the parser. If a user writes a macro that infinitely expands into itself at compile time, the compiler will hang and crash. **This is considered a skill issue, not a compiler bug.** The compiler remains maximally minimal.