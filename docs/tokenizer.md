# Lexer & Tokenization Architecture

This document outlines the structural design and philosophical boundaries of the Lexer. The Lexer is the first stage of the compilation pipeline, responsible for translating a raw stream of characters into a structured sequence of discrete tokens.

## 1. The "Dumb" Lexer Philosophy (Minimalist Taxonomy)
In traditional compilers, the lexer is often responsible for identifying specific reserved keywords (e.g., categorizing `if` as a `TOKEN_IF` and `while` as a `TOKEN_WHILE`). 

Because this language relies on a dynamic Macro Registry and Top-Down Operator Precedence (Pratt Parsing), **the lexer is intentionally completely ignorant of the language's semantics and grammar.** 
*   There are no reserved keyword tokens. 
*   The taxonomy is aggressively reduced to only four fundamental states:
    1.  **`SYMBOL`**: Any punctuation or mathematical operator (`+`, `{`, `.`, `@`).
    2.  **`IDENTIFIER`**: Any alphanumeric text sequence (`x`, `int`, `if`).
    3.  **`VALUE`**: Any numeric literal.
    4.  **`EOF`**: The physical end of the file.
*   **Deferred Semantics:** The lexer does not know or care if `int` is a type, a macro, or a variable. It simply hands the `IDENTIFIER` to the Parser, which consults the active Macro Registry to determine its meaning based on the current lexical scope.

## 2. Single-Pass Sequential Consumption
The tokenizer operates as a strict, forward-only state machine (or unified pattern matcher). It consumes the raw text buffer linearly from start to finish without backtracking.
*   **Greedy Matching:** It evaluates the character stream against a unified set of rules, always matching the longest possible valid sequence (e.g., `==` is matched as a single symbol rather than two `=` symbols).
*   **Fail-Fast Unmapped Sequences:** If the lexer encounters a sequence of characters that does not match any known structural rule, it immediately throws a syntax error. It refuses to guess or silently skip malformed text.

## 3. Spatial Awareness & Coordinate Tracking
While the lexer discards non-semantic characters (like spaces and comments), it maintains a strict mathematical mapping to the original source file.
*   **Line and Column Preservation:** Every single token emitted by the lexer is permanently stamped with its exact physical `line` and `column` coordinates.
*   **Why this matters:** This spatial data is fundamentally required by the AST and Compiler backend. When a macro expands, or when the compiler encounters a Visible Mutation Guarantee (VMG) violation deep within nested inline assembly, these physical coordinates are used to trace the error back to the exact character in the user's source file.

## 4. Early Value Normalization
To keep the Parser and AST logic as clean as possible, the lexer is responsible for normalizing raw numeric strings into native machine representations immediately upon detection.
*   **Base Conversion:** The lexer detects prefixes (`0x` for hexadecimal, `0b` for binary) and automatically parses the subsequent characters in the correct base, yielding a pure integer to the parser.
*   **Ergonomic Separators:** It explicitly supports and strips out visual underscores (e.g., `1_000_000` or `0b1010_0101`), allowing programmers to write highly readable bitwise masks without complicating the parser's logic.

## 5. Whitespace and Comment Elimination
Because the language's grammar is defined entirely by operators, blocks (`{}`), and termination symbols (`;`), whitespace and comments carry zero semantic meaning.
*   The lexer safely strips out all comments (`// ...`) and whitespace sequences at the lowest possible level. 
*   Unlike languages like Python (which rely on semantic indentation), this strict stripping guarantees that the abstract syntax tree structure is entirely immune to formatting variations.