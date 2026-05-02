
# W Language: The Kernel Architecture
**Version 2.0 Blueprint**

## 1. Philosophy
W is a homoiconic, pipeline-oriented systems programming language. 
The Python compiler has **zero built-in keywords, zero built-in control flow, and zero built-in operators**. 
Everything from `+` and `*` to `if`, `while`, and `ptr[idx]` is implemented in W itself, inside the Standard Library, using compile-time AST macros and dynamic Mixfix parsing.

The Python compiler is no longer a traditional compiler; it is an **AST Rewriter** and a **Macro Assembler**.

---

## 2. The Python Codebase (What Stays & What Changes)

### Kept Intact:
* **`cpu.dll` / `libcpu.so`**: The RISC-V execution environment.
* **`main.py`**: The entry point.
* **`asm.py`**: The raw RISC-V machine code emitter.
* **`tokens.py`**: The tokenizer. (Only minor changes needed to ensure punctuation chars are clumped dynamically instead of hardcoded).
* **`platform.py` (formerly `macros.py`)**: Defines register aliases and basic platform state. Swappable later for bytecode VMs.

### Fully Rewritten:
* **`AST.py`**: Vastly simplified. Most node types (`If`, `While`, `Store`, `Assign`) are deleted. The AST only needs to understand Pipelines, Blocks, and Tokens.
* **`expression.py`**: Replaced with a dynamic Pratt Parser that reads user-defined patterns (Mixfix parsing).
* **`compiler.py`**: Split into two phases:
  1. **Comptime Interpreter:** Executes `@expr` pipelines in-memory to transform AST nodes.
  2. **Codegen:** Emits assembly for the resulting minimal pipeline trees.

---

## 3. The Core Axioms (The "Kernel")
The Python compiler only natively understands **three constructs**:

**A. The Universal Pipeline**
The only way to move data or create scope.
`out = (in) : { body }`

**B. Hardware Intrinsics**
Direct communication with the platform backend (RISC-V).
`@asm(instruction, args...)`

**C. Compile-Time Macros (The Extensibility Engine)**
The mechanism that teaches the parser how to read new syntax and what AST to generate.
`@expr(precedence, pattern...) : out[AST] = (args[AST]) : { ... }`

---

## 4. The Mixfix Parser (`@expr`)
You can define any syntax by passing a **pattern** to `@expr`. 
The parser categorizes the pattern based on its first element:
* **NUD (Null Denotation):** Pattern starts with a literal symbol (e.g., `*`, `[`). It does not require a left-hand side.
* **LED (Left Denotation):** Pattern starts with an AST Hole (e.g., `lhs`). It binds to the expression immediately preceding it.

### Example 1: Infix Operators (LED)
Teaching the compiler how to do addition.
```w
// Pattern: AST Hole (`a`), Literal (`+`), AST Hole (`b`)
@expr(4, a, +, b) : out[AST] = (a[AST], b[AST]) : {
    @asm(add, out, a, b);
}
```

### Example 2: Prefix Operators (NUD)
Teaching the compiler how to negate a value
```w
// Pattern: Literal (`not`), AST Hole (`a`)
@expr(7, not, value) : out[AST] = (a[AST]) : {
    @asm(sub, out, 0, a);
}
```

### Example 3: Custom Control Flow (Syntactic Sugar)
Because AST blocks are implicitly quoted, we can build high-level syntax without touching Python.

```w
// Ternary Operator
@expr(2, cond, ?, t_val, :, f_val) : out[AST] = (cond[AST], t_val[AST], f_val[AST]) : {
    outr = {
        res = (cond == 1) : { t_val }
        res = (cond == 0) : { f_val }
    }
    out = outr.tes(cond)
}

// Standard IF/ELSE statement!
@expr(1, if, cond,{, t_body,}, else, {, f_body, }) : out[AST] = (cond[AST], t_body[AST], f_body[AST]) : {
    outr = {
        res = (cond == 1) : { t_body }
        res = (cond) : { f_body }
    }
    out = outr.tes(cond)
}
```

---

## 5. The Compilation Pipeline (How Python handles it)

1. **Tokenization:** `tokens.py` converts the text into `Identifier`, `Symbol`, and `Value` objects.
2. **Parser Registration:** Python scans the top-level tokens. When it sees an `@expr` definition, it registers the pattern into the `ExpressionParser`'s dynamic NUD/LED tables.
3. **AST Construction:** `expression.py` parses the file. When it hits a registered pattern (like `a + b`), it captures the `a` and `b` AST nodes.
4. **Macro Expansion:** Python pauses standard compilation, feeds `a` and `b` into the W pipeline defined in the `@expr`, and executes it in memory. The result is a standard pipeline AST.
5. **Codegen:** `compiler.py` receives a tree containing purely Pipelines, Blocks, and `@asm` calls, and translates it to `platform.py` / `asm.py` calls.
```

### A Note on the Upcoming Rewrite
Because you are keeping `tokens.py` and `asm.py`, your rewrite is strictly focused on the "middle" of the compiler (`expression.py`, `AST.py`, `compiler.py`). 

Your next logical step is to write the new `AST.py` (which will be incredibly small now—just Pipelines, Blocks, and generic Expressions) and the new `expression.py` (which will be a generic Pratt parser with a dictionary of rules instead of hardcoded `parse_Symbol_Dot` functions). 



q In @expr(4, a, +, b) : out[AST] = (a[AST], b[AST]) : { ... }, how does the compiler parser definitively know that a and b are expression holes, while + is a literal token to match?
The compiler infers it from the pipeline binding. It looks at (a[AST], b[AST]), sees a and b, and treats those specific identifiers as holes in the pattern. Everything else in the pattern is treated as a literal token.
a it will gather all, the ones that aren't found by name in bindings are symbols.

qThe macro defines precedence (e.g., 4), but what about associativity? Should the Pratt parser assume all dynamic @expr operations are Left-Associative (so a - b - c parses as (a - b) - c), or do you want a mechanism to define Right-Associativity (like for a ^ power operator)?
afor now i'll assume the order in expr is strict, multifunction can handle associativity later on?

q Are { and } just Mixfix Literals now?
In your if / else example: @expr(1, if, cond, {, t_body, }, else, {, f_body, })
Previously, the parser had hardcoded logic where { ... } automatically built a Block node. Under this new kernel architecture, does the Pratt parser treat { and } as just regular tokens matched by the macro? If so, does the compiler still natively know what a Block is, or does the pipeline body just evaluate a raw sequence of expressions?

a i was pseudo thinking about
@expr(1, if, cond, t_body, else, f_body) : out[AST] = (cond[AST], t_body[block], f_body[block])
but then again. i would like being able to define {}... i don't see a version where "[]view {}context ()binding" aren't defined before hand. so i'll just add that to the list of implicit types. you can still write @expr(1, if, cond, {,t_body,}) it'll just be handled as a block.


q In the IF example: _ = (0 : cond) : { t_body }
Are the = (assignment) and : (dataflow/range) operators baked into the Core Axioms of the compiler's pipeline parser, or are they also expected to be defined via @expr? (I assume out = (bindings) : { body } is the one hardcoded structural grammar the Python compiler natively looks for).
a the language works as is written, this refactor is to simplify everything i can out of the python definition out into the .w definition. i don't think i'll be able to move this piece easily.

q Minor changes to tokens.py
You mentioned minor changes to tokens.py to cluster punctuation dynamically. Do you want me to update tokens.py in the same batch as AST.py, expression.py, and compiler.py, or will we handle tokens later?
a save that for later. i'll do it when i rewrite the lang in it's self probably.

