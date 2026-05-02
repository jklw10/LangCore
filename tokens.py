import re
from enum import Enum, auto
from dataclasses import dataclass
from typing import Any

class TokenType(Enum):
    SYMBOL = auto()
    IDENTIFIER = auto()
    VALUE = auto()
    EOF = auto()

@dataclass(frozen=True)
class Token:
    type: TokenType
    value: Any
    line: int
    col: int

    def __repr__(self):
        return f"{self.type.name}('{self.value}') at {self.line}:{self.col}"

# A unified regex that captures tokens sequentially
TOKEN_PATTERN = re.compile(
    r'(?P<COMMENT>//.*)|'
    r'(?P<WS>\s+)|'
    r'(?P<SYMBOL>==|!=|<=|>=|[*()\^/=\+\-!|&<>\[\]{}:;,.@?])|'
    r'(?P<HEX>0x[0-9a-fA-F_]+)|'
    r'(?P<BIN>0b[01_]+)|'
    r'(?P<DEC>[0-9][0-9_]*)|'
    r'(?P<IDENT>[a-zA-Z_][a-zA-Z0-9_]*)'
)

def tokenize(text: str) -> list[Token]:
    tokens_out =[]
    line = 1
    line_start = 0

    for mo in TOKEN_PATTERN.finditer(text):
        kind = mo.lastgroup
        val = mo.group()
        col = mo.start() - line_start + 1

        if kind == 'COMMENT':
            continue
        elif kind == 'WS':
            if '\n' in val:
                line += val.count('\n')
                line_start = mo.start() + val.rfind('\n') + 1
            continue
        elif kind == 'SYMBOL':
            tokens_out.append(Token(TokenType.SYMBOL, val, line, col))
        elif kind in ('HEX', 'BIN', 'DEC'):
            clean_val = val.replace('_', '')
            base = 16 if kind == 'HEX' else (2 if kind == 'BIN' else 10)
            tokens_out.append(Token(TokenType.VALUE, int(clean_val, base), line, col))
        elif kind == 'IDENT':
            tokens_out.append(Token(TokenType.IDENTIFIER, val, line, col))
        else:
            raise SyntaxError(f"Lexer Error: Unexpected sequence '{val}' at line {line}, col {col}")

    tokens_out.append(Token(TokenType.EOF, "EOF", line, len(text) - line_start + 1))
    return tokens_out
