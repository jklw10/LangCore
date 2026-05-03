import copy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Any, Optional, Dict
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
    type_name: str = None  # New: tracks the comptime type identifier (e.g. "bool")
    line: int = 0
    col: int = 0

class MacroRule:
    def __init__(self, prec, pattern, holes, out_name, body, hole_types=None, out_type=None):
        self.prec = prec
        self.pattern = pattern
        self.holes = holes
        self.out_name = out_name
        self.body = body
        self.hole_types = hole_types or {} # Map of hole_name -> required type (e.g. {'cond': 'bool'})
        self.out_type = out_type           # Return type of the macro (e.g. 'bool')

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
            
    new_node = copy.copy(node) # Shallow copy keeps type_name
    if getattr(new_node, 'left', None):
        new_node.left = substitute_ast(new_node.left, captured)
    if getattr(new_node, 'right', None):
        new_node.right = substitute_ast(new_node.right, captured)
    if getattr(new_node, 'children', None):
        new_node.children =[substitute_ast(c, captured) for c in new_node.children]
    return new_node


class Parser:
    def __init__(self, token_list, registry, skip_blocks=False, type_env=None):
        self.tokens = token_list
        self.i = 0
        self.registry = registry
        self.skip_blocks = skip_blocks
        
        # Scope stack for type definitions (starts with global_types if passed)
        self.type_scopes =[type_env.copy() if type_env else {}]

    def declare_type(self, name, type_name):
        if name and type_name:
            self.type_scopes[-1][name] = type_name

    def get_type(self, name):
        for scope in reversed(self.type_scopes):
            if name in scope:
                return scope[name]
        return None

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
            if t.value == '[': return 50
            if t.value == '.': return 60 
            if t.value in self.registry.led_rules:
                return max(r.prec for r in self.registry.led_rules[t.value])
        return 0

    def parse_program(self):
        root = ASTNode(NodeType.Program, line=1, col=1)
        while self.peek():
            stmt = self.parse_expr()
            if stmt: 
                root.children.append(stmt)
            self.match(';')
        return root

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
                
                # Discovery Pass explicitly ignores blocks to save extreme amounts of compute
                if self.skip_blocks:
                    depth = 1
                    while self.peek():
                        nxt = self.consume()
                        if getattr(nxt, 'value', None) == '{': depth += 1
                        elif getattr(nxt, 'value', None) == '}': 
                            depth -= 1
                            if depth == 0: break
                    return block

                self.type_scopes.append({})
                while self.peek() and not getattr(self.peek(), 'value', None) == '}':
                    stmt = self.parse_expr()
                    if stmt: block.children.append(stmt)
                    self.match(';') 
                self.consume() # consume '}'
                self.type_scopes.pop()
                return block

            if t.value == '(':
                if self.peek() and getattr(self.peek(), 'value', None) == ')':
                    self.consume()
                    return ASTNode(NodeType.Tuple, children=[], line=t.line, col=t.col)
                expr = self.parse_expr(0)
                self.match(')')
                return expr

            # Array Deref (e.g. `[ptr]`)
            if t.value == '[':
                expr = self.parse_expr()
                self.match(']')
                return ASTNode(NodeType.Deref, left=expr, line=t.line, col=t.col)
            if t.value == '.':
                next_t = self.consume()
                if getattr(next_t, 'value', None) == '@':
                    name_t = self.consume(TokenType.IDENTIFIER)
                    if name_t.value == 'expr':
                        return self.parse_macro_def(name_t)
                    elif name_t.value == 'asm':
                        return self.parse_asm_intrinsic(name_t)
                elif getattr(next_t, 'type', None) == TokenType.IDENTIFIER:
                    node = ASTNode(NodeType.Identifier, value="." + next_t.value, line=t.line, col=t.col)
                    node.type_name = self.get_type("." + next_t.value)
                    return node
                raise SyntaxError(f"Unexpected token after '.' at line {t.line}:{t.col}")
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
                    while self.peek() and not getattr(self.peek(), 'value', None) == ')':
                        path_tokens.append(str(getattr(self.consume(), 'value', '')))
                    self.match(')')
                    path = "".join(path_tokens)
                    return ASTNode(NodeType.Intrinsic, value=next_t.value, children=[path], line=t.line, col=t.col)
                else:
                    raise SyntaxError(f"Unknown intrinsic @{next_t.value} at line {next_t.line}:{next_t.col}")
            
            if t.value in self.registry.nud_rules:
                return self.expand_macro(self.registry.nud_rules[t.value], t, None)

        elif (t.type == TokenType.IDENTIFIER):
            if t.value in self.registry.nud_rules:
                return self.expand_macro(self.registry.nud_rules[t.value], t, None)
            
            node = ASTNode(NodeType.Identifier, value=t.value, line=t.line, col=t.col)
            node.type_name = self.get_type(t.value) # Hooking up type-awareness to identifers
            return node

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
                    call_node = ASTNode(NodeType.Call, value=left.value, children=args, line=t.line, col=t.col)
                    call_node.type_name = self.get_type(left.value) # Propagating return type dynamically
                    return call_node
                else:
                    raise SyntaxError(f"Syntax Error at line {t.line}:{t.col} -> Cannot call non-identifier {getattr(left, 'value', left)}")

            # Type casting postfix `res[int]`
            if t.value == '[':
                type_expr = self.parse_expr(0)
                self.match(']')
                
                type_name = type_expr.value if hasattr(type_expr, 'value') else str(type_expr)
                left.type_name = type_name
                
                if left.node_type == NodeType.Identifier:
                    self.declare_type(left.value, type_name)
                return left

            if t.value == '=':
                right = self.parse_expr(prec - 1)
                
                # Check for `func_name : ret_var = (args) : { body }`
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
            if t.value == '.':
                right_t = self.consume(TokenType.IDENTIFIER)
                if left.node_type == NodeType.Identifier:
                    combined = left.value + "." + right_t.value
                    node = ASTNode(NodeType.Identifier, value=combined, line=t.line, col=t.col)
                    node.type_name = self.get_type(combined)
                    return node
                raise SyntaxError(f"Syntax Error: Can only use '.' on identifiers at {t.line}:{t.col}")
            if t.value in self.registry.led_rules:
                rules =[r for r in self.registry.led_rules[t.value] if r.prec == prec]
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
                    expected_left = rule.hole_types.get(rule.pattern[0])
                    if expected_left and left.type_name != expected_left:
                        raise SyntaxError(f"Macro type mismatch: '{rule.pattern[0]}' expected [{expected_left}], got [{left.type_name}]")
                    captured[rule.pattern[0]] = left
                    start_idx = 2 
                
                for p in rule.pattern[start_idx:]:
                    if p in rule.holes:
                        arg_node = self.parse_expr(rule.prec)
                        expected_type = rule.hole_types.get(p)
                        
                        if expected_type and getattr(arg_node, 'type_name', None) != expected_type:
                            raise SyntaxError(f"Macro type mismatch: '{p}' expected[{expected_type}], got [{getattr(arg_node, 'type_name', None)}]")
                            
                        captured[p] = arg_node
                    else:
                        act = self.consume()
                        if act is None or getattr(act, 'value', str(act)) != p:
                            raise SyntaxError(f"Macro pattern expected '{p}', got '{act}' at line {getattr(act, 'line', 'EOF')}:{getattr(act, 'col', 'EOF')}")
                
                expanded_body = substitute_ast(rule.body, captured)
                return ASTNode(NodeType.MacroCall, value=rule.out_name, left=expanded_body, type_name=rule.out_type, line=token.line, col=token.col)
            
            except SyntaxError as e:
                last_error = e
                self.i = saved_i # BACKTRACK AND TRY NEXT MACRO!
                
        raise last_error


    def parse_macro_def(self, token):
        self.match('(')
        prec = self.consume(TokenType.VALUE).value
        
        pattern =[]
        if self.match(','):
            while self.peek() and not getattr(self.peek(), 'value', None) == ')':
                tok = self.consume()
                if getattr(tok, 'value', None) != ',':
                    pattern.append(getattr(tok, 'value', str(tok)))
            self.match(')')
        else:
            self.match(')')
            while self.peek() and getattr(self.peek(), 'value', None) != ':':
                tok = self.consume()
                pattern.append(getattr(tok, 'value', str(tok)))
                
        self.match(':')
        out_name_tok = self.consume(TokenType.IDENTIFIER)
        out_name = out_name_tok.value
        out_type = None
        
        # Capture return type
        if self.match('['):
            out_type = self.consume(TokenType.IDENTIFIER).value
            self.match(']')
            
        self.match('=')
        self.match('(')
        holes =[]
        hole_types = {}
        
        while self.peek() and not getattr(self.peek(), 'value', None) == ')':
            tok = self.consume()
            if tok.type == TokenType.IDENTIFIER:
                holes.append(tok.value)
                
                # Capture typed arguments dynamically 
                if self.match('['):
                    t_type = self.consume(TokenType.IDENTIFIER).value
                    hole_types[tok.value] = t_type
                    self.match(']')
            elif tok.type == TokenType.SYMBOL and tok.value == ',':
                continue
                
        self.match(':')
        body = self.parse_expr()
        
        rule = MacroRule(prec, pattern, holes, out_name, body, hole_types, out_type)
        self.registry.register(rule)
        return ASTNode(NodeType.MacroDef, macro_rule=rule, line=token.line, col=token.col)

    def parse_asm_intrinsic(self, token):
        self.match('(')
        inst_name = self.consume(TokenType.IDENTIFIER).value
        args =[]
        while self.peek() and not getattr(self.peek(), 'value', None) == ')':
            if self.match(','): 
                continue
            args.append(self.parse_expr(30))
        self.match(')')
        return ASTNode(NodeType.Intrinsic, value="asm", children=[ASTNode(NodeType.Identifier, value=inst_name)] + args, line=token.line, col=token.col)


# Main Entry Point Function for single-pass contexts (Deprecated, mostly kept for backward compatibility)
def parse(token_list, registry=None, skip_blocks=False, type_env=None):
    if registry is None: 
        registry = MacroRegistry()
    p = Parser(token_list, registry, skip_blocks, type_env)
    return p.parse_program()