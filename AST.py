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
    Call = auto()            
    FunctionDef = auto()    
    CallerContext = auto()  
    Lens = auto()               

@dataclass
class ASTNode:
    node_type: NodeType
    value: Any = None
    left: Optional['ASTNode'] = None
    right: Optional['ASTNode'] = None
    children: List['ASTNode'] = field(default_factory=list)
    macro_rule: Any = None
    type_name: str = None  
    is_pure: bool = False  
    macro_scope: Any = None
    is_comptime_safe: bool = None 
    line: int = 0
    col: int = 0
    
    def is_body_pure(self) -> bool:
        """Return True if the AST subtree contains no visible mutation."""
        if self is None:
            return True
        if self.node_type == NodeType.Assignment:
            if getattr(self.left, 'node_type', None) == NodeType.Lens and self.left.left is None:
                return False
        if self.node_type == NodeType.Intrinsic and self.value == "asm":
            if self.children and self.children[0].value in ("store", "sw", "sh", "sb", "ecall",): 
                return False
        
        for child in getattr(self, 'children', []):
            if isinstance(child, ASTNode) and not child.is_body_pure():
                return False
        if getattr(self, 'left', None) and isinstance(self.left, ASTNode) and not self.left.is_body_pure():
            return False
        if getattr(self, 'right', None) and isinstance(self.right, ASTNode) and not self.right.is_body_pure():
            return False
        return True

class MacroRule:
    def __init__(self, prec, pattern, holes, out_name, body, hole_types=None, out_type=None, is_mutating=False):
        self.prec = prec
        self.pattern = pattern
        self.holes = holes
        self.out_name = out_name
        self.body = body
        self.hole_types = hole_types or {} 
        self.out_type = out_type           
        self.is_mutating = is_mutating   

class MacroRegistry:
    def __init__(self):
        self.nud_rules = [{}]
        self.led_rules = [{}]

    def push_scope(self):
        self.nud_rules.append({})
        self.led_rules.append({})

    def pop_scope(self):
        if len(self.nud_rules) > 1:
            self.nud_rules.pop()
            self.led_rules.pop()

    def register(self, rule):
        first = rule.pattern[0]
        if first in rule.holes:
            if len(rule.pattern) > 1:
                self.led_rules[-1].setdefault(rule.pattern[1],[]).append(rule)
            else:
                raise SyntaxError("LED macro pattern must have at least one literal trigger token")
        else:
            self.nud_rules[-1].setdefault(first,[]).append(rule)

    def get_nud(self, token_val):
        for scope in reversed(self.nud_rules):
            if token_val in scope:
                return scope[token_val]
        return None

    def get_led(self, token_val):
        for scope in reversed(self.led_rules):
            if token_val in scope:
                return scope[token_val]
        return None

def build_type_name(node):
    """Safely constructs a string representation of complex AST types like [0:1]"""
    assert node is None or isinstance(node, ASTNode) or isinstance(node, str), f"build_type_name expected ASTNode or str, got {type(node)}"
    
    #if not node: return ""
    if getattr(node, 'node_type', None) == NodeType.Identifier: return node.value
    if getattr(node, 'node_type', None) == NodeType.Value: return str(node.value)
    if getattr(node, 'node_type', None) == NodeType.Pipeline:
        return f"{build_type_name(node.left)}:{build_type_name(node.right)}"
    if getattr(node, 'node_type', None) == NodeType.Tuple:
        return ",".join(build_type_name(c) for c in node.children)
    return str(getattr(node, 'value', node))

def substitute_ast(node, captured):
    assert isinstance(captured, dict), f"substitute_ast requires a dictionary of captured bindings, got {type(captured)}"
    if node is None:
        return None
        
    if hasattr(node, 'value') and not isinstance(node, ASTNode):
        if node.value in captured:
            copied = copy.deepcopy(captured[node.value])
            assert isinstance(copied, ASTNode), "Captured value to substitute must be an ASTNode"
            return ASTNode(NodeType.CallerContext, left=copied, line=getattr(node, 'line', 0), col=getattr(node, 'col', 0))
        return node
        
    if isinstance(node, ASTNode) and node.node_type == NodeType.Identifier:
        if node.value in captured:
            copied = copy.deepcopy(captured[node.value])
            assert isinstance(copied, ASTNode), "Captured value to substitute must be an ASTNode"
            return ASTNode(NodeType.CallerContext, left=copied, line=node.line, col=node.col)
            
    new_node = copy.copy(node) 
    if getattr(new_node, 'left', None):
        new_node.left = substitute_ast(new_node.left, captured)
        assert isinstance(new_node.left, ASTNode), "Substituted left child must be an ASTNode"
    if getattr(new_node, 'right', None):
        new_node.right = substitute_ast(new_node.right, captured)
        assert isinstance(new_node.right, ASTNode), "Substituted right child must be an ASTNode"
    if getattr(new_node, 'children', None):
        new_node.children = [substitute_ast(c, captured) for c in new_node.children]
        assert all(isinstance(c, ASTNode) for c in new_node.children), "All substituted children must be ASTNodes"
        
    return new_node


class Parser:
    def __init__(self, token_list, registry, skip_blocks=False, type_env=None, exported_macros=None, import_callback=None):
        self.tokens = token_list
        self.i = 0
        self.registry = registry
        self.skip_blocks = skip_blocks
        self.type_scopes = [type_env.copy() if type_env else {}]
        self.exported_macros = exported_macros if exported_macros is not None else {}
        self.import_callback = import_callback

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
        assert expected_type is None or isinstance(expected_type, TokenType), f"consume expected TokenType Enum, got {type(expected_type)}"
        assert self.i >= 0, f"Token index out of bounds: {self.i}"

        if self.i >= len(self.tokens): return None
        t = self.tokens[self.i]
        assert hasattr(t, 'type') and hasattr(t, 'line') and hasattr(t, 'col'), "Token object is missing required attributes"

        if t.type == TokenType.EOF:
            if expected_type:
                raise SyntaxError(f"Unexpected EOF waiting for {expected_type.name}")
            return None

        if expected_type and t.type != expected_type:
            raise SyntaxError(f"Syntax Error at line {t.line}:{t.col} -> Expected {expected_type.name}, got {t.type.name}('{t.value}')")
        
        self.i += 1
        return t

    def match(self, sym_str):
        assert isinstance(sym_str, str), f"match() requires a string symbol, got {type(sym_str)}"
        t = self.peek()
        if t and t.type == TokenType.SYMBOL and t.value == sym_str:
            self.i += 1
            return True
        return False

    def get_led_prec(self, t):
        assert t is not None, "get_led_prec cannot evaluate a None token"
        assert hasattr(t, 'type') and hasattr(t, 'value'), "get_led_prec requires a valid Token object"
        
        if (t.type == TokenType.SYMBOL):
            if t.value == '=': return 5   
            if t.value == ',': return 6  
            if t.value == ':': return 20  
            if t.value == '(': return 40   
            if t.value == '[': return 50
            if t.value == '.': return 60 
            
            rules = self.registry.get_led(t.value)
            if rules:
                return max(r.prec for r in rules)
        return 0

    def parse_program(self):
        assert self.tokens is not None, "Parser initialized without tokens"
        root = ASTNode(NodeType.Program, line=1, col=1)
        while self.peek():
            stmt = self.parse_expr()
            if stmt: 
                assert isinstance(stmt, ASTNode), f"parse_expr() must return an ASTNode, got {type(stmt)}"
                root.children.append(stmt)
            self.match(';')
        return root

    def parse_expr(self, rbp=0):
        assert isinstance(rbp, (int, float)) and rbp >= 0, f"Right-binding power must be non-negative, got {rbp}"
        
        t = self.consume()
        if not t: return None
        
        left = self.nud(t)
        assert left is None or isinstance(left, ASTNode), f"nud() must return an ASTNode or None, got {type(left)}"
        
        while True:
            next_t = self.peek()
            if not next_t: break
            
            prec = self.get_led_prec(next_t)
            assert isinstance(prec, (int, float)) and prec >= 0, f"Precedence must be a non-negative number, got {prec}"
            
            if prec == 0 or rbp >= prec: break
            
            if next_t.value == '(' and getattr(left, 'node_type', None) != NodeType.Identifier:
                break
                
            self.consume()
            left = self.led(left, next_t, prec)
            assert isinstance(left, ASTNode), f"led() must return an ASTNode, got {type(left)}"
            
        return left

    def nud(self, t):
        assert t is not None, "nud() called with None token"
        assert hasattr(t, 'type') and hasattr(t, 'value'), "nud() requires a valid Token object"
        
        if (t.type == TokenType.SYMBOL):
            if t.value == '{':
                block = ASTNode(NodeType.Block, line=t.line, col=t.col)
                if self.skip_blocks:
                    depth = 1
                    while self.peek():
                        nxt = self.consume()
                        if getattr(nxt, 'value', None) == '{': depth += 1
                        elif getattr(nxt, 'value', None) == '}': 
                            depth -= 1
                            if depth == 0: break
                    return block

                self.registry.push_scope()
                self.type_scopes.append(self.type_scopes[-1].copy()) 
                
                while self.peek() and not getattr(self.peek(), 'value', None) == '}':
                    stmt = self.parse_expr()
                    if stmt: 
                        assert isinstance(stmt, ASTNode), f"Block child must be an ASTNode, got {type(stmt)}"
                        block.children.append(stmt)
                    self.match(';') 
                
                closing_brace = self.consume()
                assert closing_brace is not None and closing_brace.value == '}', "Block did not end with '}'"
                
                captured_nud = {k: list(v) for k, v in self.registry.nud_rules[-1].items()}
                captured_led = {k: list(v) for k, v in self.registry.led_rules[-1].items()}
                block.macro_scope = (captured_nud, captured_led)
                
                self.type_scopes.pop()
                self.registry.pop_scope()
                return block

            if t.value == '(':
                if self.peek() and getattr(self.peek(), 'value', None) == ')':
                    self.consume()
                    return ASTNode(NodeType.Tuple, children=[], line=t.line, col=t.col)
                expr = self.parse_expr(0)
                assert expr is not None, "Empty expression inside parentheses"
                self.match(')')
                return expr

            if t.value == '[':
                expr = self.parse_expr()
                assert expr is not None, "Lens requires a valid expression inside brackets"
                self.match(']')
                return ASTNode(NodeType.Lens, left=None, right=expr, line=t.line, col=t.col)
                
            if t.value == '.':
                next_t = self.consume()
                assert next_t is not None, "Unexpected EOF after '.'"
                if getattr(next_t, 'value', None) == '@':
                    name_t = self.consume(TokenType.IDENTIFIER)
                    assert name_t is not None, "Expected identifier after '.@'"
                    if name_t.value == 'expr':
                        return self.parse_macro_def(name_t)
                    elif name_t.value == 'asm':
                        return self.parse_asm_intrinsic(name_t)
                elif getattr(next_t, 'type', None) == TokenType.IDENTIFIER:
                    node = ASTNode(NodeType.Identifier, value="." + next_t.value, line=t.line, col=t.col)
                    node.type_name = self.get_type("." + next_t.value)
                    return node
                raise SyntaxError(f"Unexpected token after '.' at line {t.line}:{t.col}")
                
            if t.value == '@':
                next_t = self.consume(TokenType.IDENTIFIER)
                assert next_t is not None, "Expected identifier after '@'"
                if next_t.value == 'expr':
                    return self.parse_macro_def(t)
                elif next_t.value == 'asm':
                    return self.parse_asm_intrinsic(t)
                elif next_t.value in ('import', 'embed', 'using'):
                    self.match('(')
                    path_tokens =[]
                    while self.peek() and not getattr(self.peek(), 'value', None) == ')':
                        path_tokens.append(str(getattr(self.consume(), 'value', '')))
                    self.match(')')
                    
                    path_str = "".join(path_tokens)
                    assert path_str, "Path string cannot be empty in import/embed/using"
                    
                    if next_t.value == 'import' and self.import_callback:
                        assert isinstance(path_str, str) and path_str, "Macro import bounds structurally require validated file mapping paths"
                        self.import_callback(path_str)
                    
                    if next_t.value == 'using' and path_str in self.exported_macros:
                        cnud, cled = self.exported_macros[path_str]
                        for k, v in cnud.items():
                            self.registry.nud_rules[-1].setdefault(k,[]).extend(v)
                        for k, v in cled.items():
                            self.registry.led_rules[-1].setdefault(k,[]).extend(v)
                            
                    path_node = ASTNode(NodeType.Value, value=path_str, line=t.line, col=t.col)
                    return ASTNode(NodeType.Intrinsic, value=next_t.value, children=[path_node], line=t.line, col=t.col)
                else:
                    raise SyntaxError(f"Unknown intrinsic @{next_t.value} at line {next_t.line}:{next_t.col}")
            
            rules = self.registry.get_nud(t.value)
            if rules:
                return self.expand_macro(rules, t, None)

        elif (t.type == TokenType.IDENTIFIER):
            rules = self.registry.get_nud(t.value)
            if rules:
                return self.expand_macro(rules, t, None)
            
            node = ASTNode(NodeType.Identifier, value=t.value, line=t.line, col=t.col)
            node.type_name = self.get_type(t.value)
            return node

        elif (t.type == TokenType.VALUE):
            return ASTNode(NodeType.Value, value=t.value, line=t.line, col=t.col)

        raise SyntaxError(f"Unexpected token {t} at line {t.line}:{t.col}")
    
    def led(self, left, t, prec):
        assert left is not None and isinstance(left, ASTNode), "led() requires a valid left ASTNode"
        assert t is not None, "led() called with None token"
        assert isinstance(prec, (int, float)) and prec > 0, "led() called with invalid precedence"

        if (t.type == TokenType.SYMBOL):
            if t.value == '(':
                args = list()
                if self.peek() and getattr(self.peek(), 'value', None) != ')':
                    arg_node = self.parse_expr(0)
                    assert arg_node is not None, "Call arguments cannot be empty if parentheses are open"
                    if getattr(arg_node, 'node_type', None) == NodeType.Tuple:
                        args = arg_node.children
                    else:
                        args = [arg_node]
                self.match(')')
                
                if left.node_type == NodeType.Identifier:
                    call_node = ASTNode(NodeType.Call, value=left.value, children=args, line=t.line, col=t.col)
                    call_node.type_name = self.get_type(left.value)
                    return call_node
                else:
                    raise SyntaxError(f"Syntax Error at line {t.line}:{t.col} -> Cannot call non-identifier {getattr(left, 'value', left)}")

            if t.value == '[':
                inner_expr = self.parse_expr(0)
                assert inner_expr is not None, "Bracket cannot be empty"
                self.match(']')
                
                is_slice = False
                if inner_expr.node_type == NodeType.Pipeline: 
                    is_slice = True
                elif inner_expr.node_type == NodeType.Value and isinstance(inner_expr.value, int):
                    is_slice = True

                if is_slice:
                    return ASTNode(NodeType.Lens, left=left, right=inner_expr, line=t.line, col=t.col)

                type_name = build_type_name(inner_expr)
                assert type_name, "Failed to resolve type name from annotation"
                left.type_name = type_name
                
                if left.node_type == NodeType.Identifier:
                    self.declare_type(left.value, type_name)
                return left

            if t.value == '=':
                right = self.parse_expr(prec - 1)
                assert right is not None, "Assignment requires a valid right-hand expression"
                
                is_func = False
                func_name = None
                ret_node = None
                
                if left.node_type == NodeType.Pipeline and \
                   left.left.node_type == NodeType.Identifier and \
                   left.right.node_type in (NodeType.Identifier, NodeType.Tuple, NodeType.Lens):
                    is_func = True
                    func_name = left.left.value
                    ret_node = left.right
                elif left.node_type == NodeType.Tuple and len(left.children) > 0 and \
                     left.children[0].node_type == NodeType.Pipeline and \
                     left.children[0].left.node_type == NodeType.Identifier:
                    is_func = True
                    func_name = left.children[0].left.value
                    ret_children = [left.children[0].right] + left.children[1:]
                    ret_node = ASTNode(NodeType.Tuple, children=ret_children, line=left.line, col=left.col)

                if is_func:
                    if right.node_type == NodeType.Pipeline and right.right.node_type == NodeType.Block:
                        assert ret_node is not None, "Function definition requires valid return mapping"
                        func_node = ASTNode(NodeType.FunctionDef, 
                                       value=func_name, 
                                       left=ret_node, 
                                       right=right.left, 
                                       children=[right.right],
                                       line=t.line, col=t.col)
                        
                        if right.right.macro_scope:
                            self.exported_macros[func_name] = right.right.macro_scope
                            
                        return func_node
                                       
                return ASTNode(NodeType.Assignment, left=left, right=right, line=t.line, col=t.col)

            if t.value == ':':
                right = self.parse_expr(prec - 1)
                assert right is not None, "Pipeline operator requires a valid right-hand expression"
                return ASTNode(NodeType.Pipeline, left=left, right=right, line=t.line, col=t.col)
            
            if t.value == ',':
                right = self.parse_expr(prec)
                assert right is not None, "Tuple separator requires a valid right-hand expression"
                if left.node_type == NodeType.Tuple:
                    left.children.append(right)
                    return left
                return ASTNode(NodeType.Tuple, children=[left, right], line=t.line, col=t.col)
                
            if t.value == '.':
                right_t = self.consume(TokenType.IDENTIFIER)
                assert right_t is not None, "Property access dot '.' requires a following identifier"
                if left.node_type == NodeType.Identifier:
                    combined = left.value + "." + right_t.value
                    node = ASTNode(NodeType.Identifier, value=combined, line=t.line, col=t.col)
                    node.type_name = self.get_type(combined)
                    return node
                raise SyntaxError(f"Syntax Error: Can only use '.' on identifiers at {t.line}:{t.col}")
                
            rules = self.registry.get_led(t.value)
            if rules:
                valid_rules = [r for r in rules if r.prec == prec]
                if valid_rules:
                    return self.expand_macro(valid_rules, t, left)

        raise SyntaxError(f"Unexpected infix operator {t} at line {t.line}:{t.col}")
    def expand_macro(self, rule_list, token, left):
        assert rule_list, "expand_macro called with an empty rule_list"
        assert token is not None, "expand_macro requires a valid trigger token"
        assert left is None or isinstance(left, ASTNode), "expand_macro left operand must be an ASTNode"

        if not isinstance(rule_list, list):
            rule_list = [rule_list]
            
        last_error = None
        for rule in rule_list:
            assert hasattr(rule, 'pattern') and hasattr(rule, 'holes') and hasattr(rule, 'body'), "MacroRule is missing required fields"
            saved_i = self.i
            try:
                captured = {}
                start_idx = 1
                
                if left is not None:
                    expected_left = rule.hole_types.get(rule.pattern[0])
                    if expected_left and left.type_name and left.type_name != expected_left:
                        raise SyntaxError(f"Macro type mismatch: '{rule.pattern[0]}' expected [{expected_left}], got[{left.type_name}]")
                    captured[rule.pattern[0]] = left
                    start_idx = 2 
                
                for p in rule.pattern[start_idx:]:
                    if p in rule.holes:
                        assert isinstance(rule.prec, (int, float)), f"MacroRule {rule.out_name} has invalid precedence {rule.prec}"
                        arg_node = self.parse_expr(rule.prec)
                        assert arg_node is not None, f"Macro expected an expression for hole '{p}' but got nothing"
                        
                        expected_type = rule.hole_types.get(p)
                        
                        if expected_type and getattr(arg_node, 'type_name', None) and getattr(arg_node, 'type_name', None) != expected_type:
                            raise SyntaxError(f"Macro type mismatch: '{p}' expected[{expected_type}], got[{getattr(arg_node, 'type_name', None)}]")
                            
                        captured[p] = arg_node
                    else:
                        act = self.consume()
                        if act is None or getattr(act, 'value', str(act)) != p:
                            raise SyntaxError(f"Macro pattern expected '{p}', got '{act}' at line {getattr(act, 'line', 'EOF')}:{getattr(act, 'col', 'EOF')}")
                
                expanded_body = substitute_ast(rule.body, captured)
                assert isinstance(expanded_body, ASTNode) or expanded_body is None, "Macro expansion failed to produce a valid ASTNode"
                
                return ASTNode(NodeType.MacroCall, value=rule.out_name, left=expanded_body, type_name=rule.out_type, is_pure=not rule.is_mutating, line=token.line, col=token.col)
            
            except SyntaxError as e:
                last_error = e
                self.i = saved_i 
                
        raise last_error
    
    def parse_macro_def(self, token):
        assert token is not None, "parse_macro_def requires a valid trigger token"
        
        self.match('(')
        prec_tok = self.consume(TokenType.VALUE)
        assert prec_tok is not None, "Macro definition missing precedence value"
        prec = prec_tok.value
        
        pattern = []
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
                
        assert len(pattern) > 0, "Macro definition must have at least one token in its pattern"
        is_mutating = any(p == '=' for p in pattern)
        
        self.match(':')
        out_name_tok = self.consume(TokenType.IDENTIFIER)
        assert out_name_tok is not None, "Macro definition missing output name"
        out_name = out_name_tok.value
        out_type = None
        
        if self.match('['):
            out_type_node = self.parse_expr(0)
            assert out_type_node is not None, "Macro output type definition cannot be empty"
            out_type = build_type_name(out_type_node)
            self.match(']')
            
        self.match('=')
        self.match('(')
        holes = []
        hole_types = {}
        
        while self.peek() and not getattr(self.peek(), 'value', None) == ')':
            tok = self.consume()
            if tok.type == TokenType.IDENTIFIER:
                holes.append(tok.value)
                
                if self.match('['):
                    t_type_node = self.parse_expr(0)
                    assert t_type_node is not None, f"Type annotation for hole '{tok.value}' cannot be empty"
                    hole_types[tok.value] = build_type_name(t_type_node)
                    self.match(']')
            elif tok.type == TokenType.SYMBOL and tok.value == ',':
                continue
                
        self.match(')') 
        self.match(':')
        body = self.parse_expr()
        assert body is not None, "Macro body expression cannot be empty"
        
        # Enforce Visible Mutation Guarantee: If macro doesn't have '=', block must be pure
        #if not is_mutating and not body.is_body_pure():
        #    raise SyntaxError(f"Visible Mutation Guarantee Violation at line {token.line}:{token.col} -> Macro pattern is marked pure but body contains mutations")
        
        rule = MacroRule(prec, pattern, holes, out_name, body, hole_types, out_type, is_mutating)
        self.registry.register(rule)
        return ASTNode(NodeType.MacroDef, macro_rule=rule, line=token.line, col=token.col)

    def parse_asm_intrinsic(self, token):
        assert token is not None, "parse_asm_intrinsic requires a valid token"
        self.match('(')
        inst_name_tok = self.consume(TokenType.IDENTIFIER)
        assert inst_name_tok is not None, "@asm requires an instruction name"
        inst_name = inst_name_tok.value
        args = []
        while self.peek() and not getattr(self.peek(), 'value', None) == ')':
            if self.match(','): 
                continue
            arg_expr = self.parse_expr(30)
            assert arg_expr is not None, "Failed to parse argument in @asm intrinsic"
            args.append(arg_expr)
        self.match(')')
        return ASTNode(NodeType.Intrinsic, value="asm", children=[ASTNode(NodeType.Identifier, value=inst_name)] + args, line=token.line, col=token.col)

def parse(token_list, registry=None, skip_blocks=False, type_env=None, exported_macros=None, import_callback=None):
    if registry is None: 
        registry = MacroRegistry()
    p = Parser(token_list, registry, skip_blocks, type_env, exported_macros, import_callback)
    return p.parse_program()