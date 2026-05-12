# AST & Parser Architecture

This document outlines the structural design, parsing philosophies, and Abstract Syntax Tree (AST) mechanisms that drive the compiler. The parser converts the token stream into a dynamic, macro-expandable tree structure without relying on hardcoded keywords.

## 1. Top-Down Operator Precedence (Pratt Parsing)
Because the language lacks traditional reserved keywords and relies heavily on user-defined macros, a standard Recursive Descent parser is insufficient. The parser is built entirely on a **Pratt Parsing** model:

*   **Null Denotation (NUD):** Handles tokens that do not care about what is to their left (Prefixes, Literals, Blocks, Identifiers).
*   **Left Denotation (LED):** Handles tokens that require a left-hand operand (Infixes, Suffixes, Pipelines `:`, Assignments `=`, Method Calls `.`, Lenses `[]`).
*   **Dynamic Precedence:** Every operator or macro has a binding power (precedence level). Expressions are parsed sequentially until an operator with a lower binding power than the current context is encountered.

## 2. Universal AST Node Structure
The language avoids disparate class hierarchies. A single, universal `ASTNode` structure represents everything from a raw integer to a complex function definition.

*   **Uniformity:** Every node has a `node_type`, an optional `left` and `right` child, an array of `children`, and structural metadata.
*   **Metadata Propagation:** Nodes track their own `type_name`, `is_pure` (mutation status), and physical `line/col` mapping. 
*   **Types as Expressions:** Type annotations (e.g., `[0:4]`) are parsed as standard AST expressions. A utility (`build_type_name`) serializes them into strings for the type environment, maintaining grammatical consistency.

## 3. The Macro Registry & Reality Rewriting
The syntax of the language mutates linearly as the file is parsed. 

*   **Lexical Scoping of Syntax:** The `MacroRegistry` operates as a strict stack. When the parser encounters a `{` block, it pushes a new environment scope.
*   **Graceful Popping:** When the parser encounters the matching `}`, the local scope is popped. Macros defined within that block cease to exist.
*   **Export Capture:** When a function or namespace block is defined, its final `MacroRegistry` state is captured and bound to its identifier. The `@using(path)` intrinsic injects a captured syntax scope back into the active registry.

## 4. AST Substitution & Hygiene (`CallerContext`)
Macros operate by structural substitution. When a macro is called, the parser captures the AST trees passed into its "holes" and recursively substitutes them into the macro's body tree.

*   **The Hygiene Problem:** Variables referenced within a macro argument could have their stack offsets evaluated in the wrong context once expanded inline.
*   **The `CallerContext` Node:** Substituted AST nodes are wrapped in a `CallerContext` boundary node. When the code generator encounters this node, it temporarily resets the compiler's purity and offset arithmetic to match the hardware state present when the macro was *called*.

## 5. Unified Construct Parsing (Functions vs. Assignments)
Because the grammar is unified under `binder : block = (bindings) : { body }`, the parser does not treat functions, namespaces, or standard variables differently at the token level.

*   **Structural Identification:** During the `=` LED parsing phase, the parser inspects the left side of the tree. If it detects a `Pipeline` node containing an `Identifier` on the left and a `Tuple` (or `Lens`/`Identifier`) on the right, it dynamically upgrades the generic assignment into a `FunctionDef` node.

## 6. Visible Mutation Tracking (VMG)
The VMG enforces state purity at the architectural level. While the AST contains `is_body_pure()` checks to structurally map if a subtree contains blind pointer dereferences or `store/sw/sb` intrinsics, the strict enforcement is largely handled by the **Compiler Backend**.
If a pure context attempts to emit mutating assembly to anything other than its designated `pure_context_out_var`, the backend immediately faults.

## 7. Intrinsics (`@` and `.@`)
The parser reserves the `@` symbol for Intrinsics to communicate directly with the compiler.

*   `.@expr`: Defines an inline macro within the registry at compile time.
*   `@asm`: Injects bare-metal hardware instructions directly into the AST.
*   `@import` / `@using`: Triggers file-system callbacks during parsing, fetching external files, parsing them into ASTs, and updating the global `MacroRegistry`.
*   `@embed`: Embeds static file data directly into the binary as `.rodata` bypassing the stack.