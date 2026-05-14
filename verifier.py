import subprocess
import sys
import os

try:
    from tokens import tokenize, TokenType
except ImportError:
    print("Error: Ensure tokens.py is in the current directory.")
    sys.exit(1)

TEST_FILE = "tests/tokenizer.w"

def run_w_compiler_tokenizer(code_str: str):
    print("Running native `.w` compiler over source code via stdin...")
    
    process = subprocess.Popen(
        ["python", "main.py", TEST_FILE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=code_str)
    
    if process.returncode != 0:
        print("Fatal .w Architecture Trap / Compilation Error:")
        print(stderr)
        # We still print stdout in case the native panic message was written there
        print(stdout)
        sys.exit(1)
        
    w_tokens = []
    
    type_map = {
        1: TokenType.SYMBOL,
        2: TokenType.IDENTIFIER,
        3: TokenType.VALUE, 
        4: TokenType.VALUE, 
        5: TokenType.EOF
    }
    
    # Parse native output stream back into python objects
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line: continue
        
        parts = line.split(":", 3)
        if len(parts) == 4:
            t_id_str, line_no, col_no, val_str = parts
            enum_type = type_map[int(t_id_str)]
            
            if int(t_id_str) == 3:
                val = int(val_str)
            elif int(t_id_str) == 4:
                # Handle string escaping
                val = val_str.encode('utf-8').decode('unicode_escape')
            elif enum_type == TokenType.EOF:
                val = "EOF"
            else:
                val = val_str 
                
            w_tokens.append((enum_type, val, int(line_no), int(col_no)))

    return w_tokens

def run_tests():
    if not os.path.exists(TEST_FILE):
        print(f"File {TEST_FILE} not found!")
        sys.exit(1)

    with open(TEST_FILE, "r") as f:
        source_code = f.read()

    print("Running baseline Python tokenizer...")
    py_tokens_raw = tokenize(source_code)
    py_formatted = [(t.type, t.value, t.line, t.col) for t in py_tokens_raw]

    w_tokens = run_w_compiler_tokenizer(source_code)

    success = True
    print(f"Comparing stream sequence: {len(py_formatted)} vs {len(w_tokens)} tokens emitted.")
    
    for i, (py_tok, w_tok) in enumerate(zip(py_formatted, w_tokens)):
        if py_tok != w_tok:
            print(f"\n[!] Divergence detected at Token Index {i}:")
            print(f"    Python RegEx:  {py_tok}")
            print(f"    W Native Code: {w_tok}")
            success = False
            break

    if len(py_formatted) != len(w_tokens):
        print(f"\n[!] Stream count mismatch: RegEx({len(py_formatted)}) vs W({len(w_tokens)})")
        success = False

    if success:
        print("\n[✔] Success: Both tokenizers are identical! W Native Code correctly implemented the RegEx pipeline.")

if __name__ == "__main__":
    run_tests()