# --- START OF FILE AST.py ---

import copy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Any, Optional
from tokens import Token, TokenType

class NodeType(Enum):
    Program = auto()
    Block = auto()
    Pipeline = auto()       
    Assignment = auto()     
    Tuple = auto()          
    Expression = auto()
    Identifier = auto()
    Value = auto()
    Intrinsic = auto()      
    MacroDef = auto()       
    MacroCall = auto()      
    Deref = auto()    
    Call = auto()            
    FunctionDef = auto()         

@dataclass
class ASTNode:
    node_type: NodeType
    value: Any = None
    left: Optional['ASTNode'] = None
    right: Optional['ASTNode'] = None
    children: List['ASTNode'] = field(default_factory=list)
    macro_rule: Any = None
    line: int = 0
    col: int = 0

class MacroRule:
    def __init__(self, prec, pattern, holes, out_name, body):
        self.prec = prec
        self.pattern = pattern
        self.holes = holes
        self.out_name = out_name
        self.body = body

class MacroRegistry:
    def __init__(self):
        self.nud_rules = {}
        self.led_rules = {}

    def register(self, rule):
        first = rule.pattern[0]
        if first in rule.holes:
            if len(rule.pattern) > 1:
                self.led_rules.setdefault(rule.pattern[1],[]).append(rule)
            else:
                raise SyntaxError("LED macro pattern must have at least one literal trigger token")
        else:
            self.nud_rules.setdefault(first,[]).append(rule)

registry = MacroRegistry()

def substitute_ast(node, captured):
    if node is None:
        return None
    if hasattr(node, 'value') and not isinstance(node, ASTNode):
        if node.value in captured:
            return copy.deepcopy(captured[node.value])
        return node
    if isinstance(node, ASTNode) and node.node_type == NodeType.Identifier:
        if node.value in captured:
            return copy.deepcopy(captured[node.value])
            
    new_node = copy.copy(node)
    if getattr(new_node, 'left', None):
        new_node.left = substitute_ast(new_node.left, captured)
    if getattr(new_node, 'right', None):
        new_node.right = substitute_ast(new_node.right, captured)
    if getattr(new_node, 'children', None):
        new_node.children =[substitute_ast(c, captured) for c in new_node.children]
    return new_node

class Parser:
    def __init__(self, token_list):
        self.tokens = token_list
        self.i = 0
        
    def peek(self):
        if self.i < len(self.tokens):
            t = self.tokens[self.i]
            if t.type != TokenType.EOF:
                return t
        return None

    def consume(self, expected_type: TokenType = None):
        if self.i >= len(self.tokens): return None
        t = self.tokens[self.i]
        
        if t.type == TokenType.EOF:
            if expected_type:
                raise SyntaxError(f"Unexpected EOF waiting for {expected_type.name}")
            return None

        if expected_type and t.type != expected_type:
            raise SyntaxError(f"Syntax Error at line {t.line}:{t.col} -> Expected {expected_type.name}, got {t.type.name}('{t.value}')")
        
        self.i += 1
        return t

    def match(self, sym_str):
        t = self.peek()
        if t and t.type == TokenType.SYMBOL and t.value == sym_str:
            self.i += 1
            return True
        return False

    def get_led_prec(self, t):
        if (t.type == TokenType.SYMBOL):
            if t.value == '=': return 10
            if t.value == ':': return 20
            if t.value == ',': return 30
            if t.value == '(': return 40   
            if t.value in registry.led_rules:
                return max(r.prec for r in registry.led_rules[t.value])
        return 0

    def parse_expr(self, rbp=0):
        t = self.consume()
        if not t: return None
        left = self.nud(t)
        
        while True:
            next_t = self.peek()
            if not next_t: break
            prec = self.get_led_prec(next_t)
            if prec == 0 or rbp >= prec: break
            
            if next_t.value == '(' and getattr(left, 'node_type', None) != NodeType.Identifier:
                break
                
            self.consume()
            left = self.led(left, next_t, prec)
            
        return left

    def nud(self, t):
        if (t.type == TokenType.SYMBOL):
            if t.value == '{':
                block = ASTNode(NodeType.Block, line=t.line, col=t.col)
                while self.peek() and not self.match('}'):
                    stmt = self.parse_expr()
                    if stmt: block.children.append(stmt)
                    self.match(';') 
                return block
            if t.value == '(':
                if self.peek() and getattr(self.peek(), 'value', None) == ')':
                    self.consume()
                    return ASTNode(NodeType.Tuple, children=[], line=t.line, col=t.col)
                expr = self.parse_expr(0)
                self.match(')')
                return expr
            if t.value == '[':
                expr = self.parse_expr()
                self.match(']')
                return ASTNode(NodeType.Deref, left=expr, line=t.line, col=t.col)

            # --- INTRINSICS & MACROS ---
            if t.value == '@':
                next_t = self.consume(TokenType.IDENTIFIER)
                if next_t.value == 'expr':
                    return self.parse_macro_def(t)
                elif next_t.value == 'asm':
                    return self.parse_asm_intrinsic(t)
                elif next_t.value in ('import', 'embed'):
                    self.match('(')
                    path_tokens =[]
                    while self.peek() and not self.match(')'):
                        path_tokens.append(str(getattr(self.consume(), 'value', '')))
                    path = "".join(path_tokens)
                    return ASTNode(NodeType.Intrinsic, value=next_t.value, children=[path], line=t.line, col=t.col)
                else:
                    raise SyntaxError(f"Unknown intrinsic @{next_t.value} at line {next_t.line}:{next_t.col}")
            
            if t.value in registry.nud_rules:
                return self.expand_macro(registry.nud_rules[t.value], t, None)

        elif (t.type == TokenType.IDENTIFIER):
            if t.value in registry.nud_rules:
                return self.expand_macro(registry.nud_rules[t.value], t, None)
            return ASTNode(NodeType.Identifier, value=t.value, line=t.line, col=t.col)

        elif (t.type == TokenType.VALUE):
            return ASTNode(NodeType.Value, value=t.value, line=t.line, col=t.col)

        raise SyntaxError(f"Unexpected token {t} at line {t.line}:{t.col}")
    
    def led(self, left, t, prec):
        if (t.type == TokenType.SYMBOL):
            if t.value == '(':
                args =[]
                if self.peek() and getattr(self.peek(), 'value', None) != ')':
                    arg_node = self.parse_expr(0)
                    if getattr(arg_node, 'node_type', None) == NodeType.Tuple:
                        args = arg_node.children
                    else:
                        args = [arg_node]
                self.match(')')
                
                if left.node_type == NodeType.Identifier:
                    return ASTNode(NodeType.Call, value=left.value, children=args, line=t.line, col=t.col)
                else:
                    raise SyntaxError(f"Syntax Error at line {t.line}:{t.col} -> Cannot call non-identifier {getattr(left, 'value', left)}")

            if t.value == '=':
                right = self.parse_expr(prec - 1)
                if left.node_type == NodeType.Pipeline and \
                   left.left.node_type == NodeType.Identifier and \
                   left.right.node_type == NodeType.Identifier:
                    if right.node_type == NodeType.Pipeline and right.right.node_type == NodeType.Block:
                        return ASTNode(NodeType.FunctionDef, 
                                       value=left.left.value, 
                                       left=left.right, 
                                       right=right.left, 
                                       children=[right.right],
                                       line=t.line, col=t.col)
                                       
                return ASTNode(NodeType.Assignment, left=left, right=right, line=t.line, col=t.col)
            if t.value == ':':
                right = self.parse_expr(prec - 1)
                return ASTNode(NodeType.Pipeline, left=left, right=right, line=t.line, col=t.col)
            if t.value == ',':
                right = self.parse_expr(prec)
                if left.node_type == NodeType.Tuple:
                    left.children.append(right)
                    return left
                return ASTNode(NodeType.Tuple, children=[left, right], line=t.line, col=t.col)
            if t.value in registry.led_rules:
                rules =[r for r in registry.led_rules[t.value] if r.prec == prec]
                if rules:
                    return self.expand_macro(rules, t, left)

        raise SyntaxError(f"Unexpected infix operator {t} at line {t.line}:{t.col}")

    def expand_macro(self, rule_list, token, left):
        if not isinstance(rule_list, list):
            rule_list =[rule_list]
            
        last_error = None
        for rule in rule_list:
            saved_i = self.i
            try:
                captured = {}
                start_idx = 1
                if left is not None:
                    captured[rule.pattern[0]] = left
                    start_idx = 2 
                
                for p in rule.pattern[start_idx:]:
                    if p in rule.holes:
                        captured[p] = self.parse_expr(rule.prec)
                    else:
                        act = self.consume()
                        if act is None or getattr(act, 'value', str(act)) != p:
                            raise SyntaxError(f"Macro pattern expected '{p}', got '{act}' at line {getattr(act, 'line', 'EOF')}:{getattr(act, 'col', 'EOF')}")
                
                expanded_body = substitute_ast(rule.body, captured)
                return ASTNode(NodeType.MacroCall, value=rule.out_name, left=expanded_body, line=token.line, col=token.col)
            
            except SyntaxError as e:
                last_error = e
                self.i = saved_i
                
        raise last_error


    def parse_macro_def(self, token):
        self.match('(')
        prec = self.consume(TokenType.VALUE).value
        
        pattern =[]
        if self.match(','):
            while self.peek() and not self.match(')'):
                tok = self.consume()
                if getattr(tok, 'value', None) != ',':
                    pattern.append(getattr(tok, 'value', str(tok)))
        else:
            self.match(')')
            while self.peek() and getattr(self.peek(), 'value', None) != ':':
                tok = self.consume()
                pattern.append(getattr(tok, 'value', str(tok)))
                
        self.match(':')
        out_name = self.consume(TokenType.IDENTIFIER).value
        
        if self.match('['):
            self.consume(TokenType.IDENTIFIER) 
            self.match(']')
            
        self.match('=')
        self.match('(')
        holes =[]
        while self.peek() and not self.match(')'):
            tok = self.consume()
            if tok.type == TokenType.IDENTIFIER:
                holes.append(tok.value)
                if self.match('['):
                    self.consume(TokenType.IDENTIFIER)
                    self.match(']')
            elif tok.type == TokenType.SYMBOL and tok.value == ',':
                continue
                
        self.match(':')
        body = self.parse_expr()
        
        rule = MacroRule(prec, pattern, holes, out_name, body)
        registry.register(rule)
        return ASTNode(NodeType.MacroDef, macro_rule=rule, line=token.line, col=token.col)

    def parse_asm_intrinsic(self, token):
        self.match('(')
        inst_name = self.consume(TokenType.IDENTIFIER).value
        args =[]
        while self.peek() and not self.match(')'):
            if self.match(','): 
                continue
            args.append(self.parse_expr(30))
        return ASTNode(NodeType.Intrinsic, value="asm", children=[ASTNode(NodeType.Identifier, value=inst_name)] + args, line=token.line, col=token.col)

def parse(token_list):
    p = Parser(token_list)
    root = ASTNode(NodeType.Program, line=1, col=1)
    while p.peek():
        stmt = p.parse_expr()
        if stmt: 
            root.children.append(stmt)
        p.match(';')
    return root