# AST & Parser Architecture

This document outlines the structural design, parsing philosophies, and Abstract Syntax Tree (AST) mechanisms that drive the compiler. The parser is responsible for converting the token stream into a dynamic, macro-expandable tree structure without relying on hardcoded keywords.

## 1. Top-Down Operator Precedence (Pratt Parsing)
Because the language lacks traditional reserved keywords (e.g., `if`, `while`, `struct`) and relies heavily on user-defined macros, a standard Recursive Descent parser is insufficient. The parser is built entirely on a **Pratt Parsing** model:

*   **Null Denotation (NUD):** Handles tokens that do not care about what is to their left (Prefixes, Literals, Blocks, Identifiers).
*   **Left Denotation (LED):** Handles tokens that require a left-hand operand (Infixes, Suffixes, Pipelines `:`, Assignments `=`, Method Calls `.`).
*   **Dynamic Precedence:** Every operator or macro has a binding power (precedence level). Expressions are parsed sequentially until an operator with a lower binding power than the current context is encountered.

This axiomatic grammar ensures that the compiler only needs to understand mathematical precedence, leaving syntax definitions entirely to the `MacroRegistry`.

## 2. Universal AST Node Structure
The language avoids disparate class hierarchies (e.g., separate classes for `IfStatement`, `WhileLoop`, `BinaryOp`). Instead, a single, universal `ASTNode` structure represents everything from a raw integer value to a complex function definition.

*   **Uniformity:** Every node has a `type`, an optional `left` and `right` child, an array of `children` (for blocks/tuples), and structural metadata.
*   **Metadata Propagation:** Nodes track their own `type_name`, `is_pure` (mutation status), and physical `line/col` mapping. 
*   **Types as Expressions:** Type annotations (e.g., `[0:4]`) are not parsed as special grammar. They are parsed as standard standard AST expressions and serialized into strings for the type environment, maintaining grammatical consistency.

## 3. The Macro Registry & Reality Rewriting
The syntax of the language is not static; it mutates linearly as the file is parsed. 

*   **Lexical Scoping of Syntax:** The `MacroRegistry` operates as a strict stack. When the parser encounters a `{` block, it pushes a new environment scope. Macros defined inside this block alter the language's grammar immediately.
*   **Graceful Popping:** When the parser encounters the matching `}`, the local scope is popped. Any macros defined within that block cease to exist, returning the language grammar to its previous state. This prevents local syntax modifications from polluting the global file space.
*   **Export Capture:** When a function or namespace block is defined, its final `MacroRegistry` state is captured and bound to its identifier. This allows statements like `@using(int)` to explicitly inject a captured syntax scope back into the active registry.

## 4. AST Substitution & Hygiene (`CallerContext`)
Macros operate by structural substitution rather than string manipulation. When a macro is called, the parser captures the actual AST trees passed into its "holes" and recursively replaces them into the macro's body tree.

*   **The Hygiene Problem:** Because a macro expands inline into the caller's block, variables referenced within the macro argument could have their stack offsets evaluated in the wrong context.
*   **The `CallerContext` Node:** To solve this, substituted AST nodes are explicitly wrapped in a `CallerContext` boundary node. When the code generator encounters this node, it temporarily resets the compiler's offset arithmetic to match the hardware stack state present at the exact moment the macro was *called*, guaranteeing memory safety.

## 5. Unified Construct Parsing (Functions vs. Assignments)
Because the grammar is unified under `binder : block = (bindings) : { body }`, the parser does not treat functions, namespaces, or standard variables differently at the token level.

*   The pipeline operator `:` and assignment operator `=` naturally build a generic AST. 
*   **Structural Identification:** During the `=` LED parsing phase, the parser inspects the left side of the tree. If it detects a `Pipeline` node containing an `Identifier` on the left and a `Tuple` on the right, it dynamically upgrades the generic assignment into a `FunctionDef` node.

## 6. Visible Mutation Tracking (VMG)
The AST actively proves the physical safety of the code during the parsing phase.

*   **`is_body_pure` Verification:** AST nodes contain recursive logic to check for state mutation. It scans the subtree for:
    1.  Blind pointer dereferencing assignments (`[ptr] = x`).
    2.  Inline assembly intrinsics invoking `store`, `sw`, or `sb`.
*   If a macro pattern is declared without the explicit mutation token `=`, but the parser detects an impure subtree, it guarantees a compile-time structural fault (The Visible Mutation Guarantee).

## 7. Intrinsics (`@`)
While the language abstracts control flow via macros, it still needs direct communication with the compiler backend. The parser reserves the `@` symbol for Intrinsics.

*   `@asm`: Injects bare-metal hardware instructions (like `add`, `jalr`, `ecall`) directly into the AST, completely bypassing language semantics.
*   `@import` / `@using`: Triggers file-system callbacks during the parsing phase, fetching external `.w` files, parsing them into ASTs, and updating the global `MacroRegistry` before continuing to parse the current file.
*   `@embed`: Embeds file data directly in the binary.