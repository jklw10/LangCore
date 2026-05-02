# --- START OF FILE compiler.py ---

import macros
import tokens
import AST
from macros import asm
from AST import NodeType, ASTNode
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class SymbolInfo:
    offset_from_base: int  

class Compiler:
    def __init__(self):
        self.scopes: List[Dict[str, SymbolInfo]] = [{}]
        self.current_stack_depth = 0
        self.label_counter = 0
        self.function_registry = {}

    def get_symbol(self, name: str) -> Optional[SymbolInfo]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def declare_symbol(self, name: str):
        info = SymbolInfo(offset_from_base=self.current_stack_depth - asm.REGISTER_SIZE)
        self.scopes[-1][name] = info
        return info

    def enter_scope(self):
        self.scopes.append({})

    def exit_scope(self):
        self.scopes.pop()

    def get_unique_label(self, prefix="lbl"):
        self.label_counter += 1
        return f"{prefix}_{self.label_counter}"

    def compile(self, node: ASTNode):
        macros.init()
        self._compile_node(node)
        return asm

    def _compile_node(self, node: ASTNode):
        if not node: return
        method_name = node.node_type.name
        visitor = getattr(self, method_name, self.error)
        return visitor(node)
        
    def error(self, node):
        raise NotImplementedError(f"No compile method for {node.node_type} at line {node.line}:{node.col}")
    
    def FunctionDef(self, node):
        func_name = node.value
        ret_var = node.left.value
        pattern_node = node.right
        body = node.children[0]
        
        if func_name not in self.function_registry:
            self.function_registry[func_name] = []
            
        self.function_registry[func_name].append({
            'ret_var': ret_var,
            'pattern': pattern_node,
            'body': body
        })

    def Call(self, node):
        func_name = node.value
        call_args = node.children
        
        defs = self.function_registry.get(func_name,[])
        for definition in defs:
            bindings, match = self._match_pattern(definition['pattern'], call_args)
            if match:
                expanded_body = AST.substitute_ast(definition['body'], bindings)
                
                self.enter_scope()
                macros.push(macros.x0)
                self.current_stack_depth += asm.REGISTER_SIZE
                out_sym = self.declare_symbol(definition['ret_var'])
                
                self._compile_node(expanded_body)
                
                offset = out_sym.offset_from_base - self.current_stack_depth
                asm.lw(macros.t0, macros.stack_ptr, offset)
                self.exit_scope()
                
                macros.pop(macros.t1) 
                self.current_stack_depth -= asm.REGISTER_SIZE
                macros.push(macros.t0)
                self.current_stack_depth += asm.REGISTER_SIZE
                
                return 
                
        raise ValueError(f"No matching signature for function '{func_name}' with args {call_args} at line {node.line}:{node.col}")

    def Program(self, node):
        for child in node.children:
            self._compile_node(child)
        asm.ecall()

    def Block(self, node):
        self.enter_scope()
        start_depth = self.current_stack_depth
        for child in node.children:
            self._compile_node(child)
        diff = self.current_stack_depth - start_depth
        if diff > 0:
            asm.addi(macros.stack_ptr, macros.stack_ptr, -diff)
            self.current_stack_depth = start_depth
        self.exit_scope()

    def MacroDef(self, node):
        pass

    def MacroCall(self, node):
        self.enter_scope()
        
        macros.push(macros.x0)
        self.current_stack_depth += asm.REGISTER_SIZE
        out_sym = self.declare_symbol(node.value)
        
        self._compile_node(node.left)
        
        offset = out_sym.offset_from_base - self.current_stack_depth
        asm.lw(macros.t0, macros.stack_ptr, offset)
        
        self.exit_scope()

        macros.pop(macros.t1) 
        self.current_stack_depth -= asm.REGISTER_SIZE

        macros.push(macros.t0)
        self.current_stack_depth += asm.REGISTER_SIZE

    def Assignment(self, node):
        if node.left.node_type == NodeType.Identifier:
            name = node.left.value
            
            if name and name.startswith(".") and getattr(self, 'current_type_context', None):
                name = self.current_type_context + name
                node.left.value = name
                
            self._compile_node(node.right)
            
            sym = self.get_symbol(name)
            if sym:
                macros.pop(macros.t0)
                self.current_stack_depth -= asm.REGISTER_SIZE
                offset = sym.offset_from_base - self.current_stack_depth
                asm.store(macros.stack_ptr, offset, macros.t0)
            else:
                self.declare_symbol(name)

        elif node.left.node_type == NodeType.Deref:
            self._compile_node(node.left.left)
            self._compile_node(node.right)
            
            macros.pop(macros.t0)
            self.current_stack_depth -= asm.REGISTER_SIZE
            
            macros.pop(macros.t1)
            self.current_stack_depth -= asm.REGISTER_SIZE
            
            asm.store(macros.t1, 0, macros.t0)
        else:
            raise SyntaxError(f"Syntax Error at line {node.line}:{node.col} -> Invalid assignment target {node.left.node_type.name}")

    def Pipeline(self, node):
        if node.right and node.right.node_type == NodeType.Block:
            self._compile_loop(node.left, node.right)
        else:
            self._compile_node(node.left)
            if node.right:
                self._compile_node(node.right)

    def _compile_loop(self, condition_node, body_node):
        l_start = self.get_unique_label("loop_start")
        l_end = self.get_unique_label("loop_end")
        
        self.enter_scope()
        start_depth = self.current_stack_depth
        
        old_type_ctx = getattr(self, 'current_type_context', None)
        old_blueprint_ctx = getattr(self, 'current_blueprint_context', None)
        self.current_type_context = None
        self.current_blueprint_context = None
        
        asm.label(l_start)
        
        if condition_node:
            conditions = condition_node.children if condition_node.node_type == NodeType.Tuple else [condition_node]
            for cond in conditions:
                self._compile_node(cond)
                macros.pop(macros.t0)
                self.current_stack_depth -= asm.REGISTER_SIZE
                asm.beq(macros.t0, macros.x0, l_end)
            
        self._compile_node(body_node)
          
        asm.jal(macros.x0, l_start)
        asm.label(l_end)
        
        diff = self.current_stack_depth - start_depth
        if diff > 0:
            asm.addi(macros.stack_ptr, macros.stack_ptr, -diff)
            self.current_stack_depth = start_depth
            
        self.exit_scope()

        self.current_type_context = old_type_ctx
        self.current_blueprint_context = old_blueprint_ctx

    def Intrinsic(self, node):
        if node.value == "asm":
            self._compile_asm(node)
        elif node.value == "embed":
            self._compile_embed(node)
        elif node.value == "import":
            self._compile_import(node)

    def _compile_import(self, node):
        path = node.children[0]
        with open(path, 'r') as f:
            source = f.read()
        imported_tokens = tokens.tokenize(source)
        imported_ast = AST.parse(imported_tokens)
        for child in imported_ast.children:
            self._compile_node(child)
        macros.push(macros.x0)
        self.current_stack_depth += asm.REGISTER_SIZE

    def _compile_embed(self, node):
        path = node.children[0]
        with open(path, "rb") as f:
            data = f.read()
        skip_label = self.get_unique_label("skip_embed")
        asm.jal(macros.t0, skip_label)
        asm.code.extend(data)
        padding = (asm.REGISTER_SIZE - (len(data) % asm.REGISTER_SIZE)) % asm.REGISTER_SIZE
        if padding > 0:
            asm.code.extend(b'\x00' * padding)
        asm.label(skip_label)
        macros.push(macros.t0)
        self.current_stack_depth += asm.REGISTER_SIZE

    def _match_pattern(self, pattern_node, call_args):
        if not pattern_node or (pattern_node.node_type == NodeType.Tuple and not pattern_node.children):
            pat_args =[]
        elif pattern_node.node_type == NodeType.Tuple:
            pat_args = pattern_node.children
        else:
            pat_args =[pattern_node]
            
        if len(pat_args) != len(call_args):
            return {}, False
            
        bindings = {}
        for p, c in zip(pat_args, call_args):
            if p.node_type == NodeType.Value:
                if c.node_type != NodeType.Value or c.value != p.value:
                    return {}, False
            elif p.node_type == NodeType.Identifier:
                bindings[p.value] = c
            else:
                return {}, False
        return bindings, True

    def _compile_asm(self, node):
        inst_name = node.children[0].value
        args =[]
        
        reg_map = macros.reg_map
        no_rd_instructions = macros.no_rd_instructions
        imm_positions = macros.imm_positions

        has_rd = inst_name not in no_rd_instructions
        
        temp_pool =[6, 7, 28, 29, 30, 31] 
        temp_idx = 0
        
        store_back_sym = None
        rd_reg_to_push = 0
        
        for i, arg in enumerate(node.children[1:]):
            if inst_name in {"jal", "bge", "beq", "bne"} and i == len(node.children[1:]) - 1:
                args.append(arg.value if hasattr(arg, 'value') else arg)
                continue

            if getattr(arg, 'node_type', None) == NodeType.Value:
                val = arg.value
                if inst_name in imm_positions and i in imm_positions[inst_name]:
                    args.append(val)
                else:
                    tmp_reg = temp_pool[temp_idx]
                    temp_idx += 1
                    macros.load_immediate(tmp_reg, val)
                    args.append(tmp_reg)
                continue
                
            name = arg.value
            if name in reg_map:
                args.append(reg_map[name])
                if i == 0 and has_rd:
                    rd_reg_to_push = reg_map[name]
            else:
                sym = self.get_symbol(name)
                is_output = (i == 0 and has_rd)
                
                if is_output:
                    if not sym:
                        macros.push(macros.x0)
                        self.current_stack_depth += asm.REGISTER_SIZE
                        sym = self.declare_symbol(name)
                    
                    args.append(5) 
                    store_back_sym = sym
                    rd_reg_to_push = 5
                else:
                    if not sym:
                        raise ValueError(f"Undefined variable read in @asm: '{name}' at line {node.line}:{node.col}")
                    
                    tmp_reg = temp_pool[temp_idx]
                    temp_idx += 1
                    
                    offset = sym.offset_from_base - self.current_stack_depth
                    asm.lw(tmp_reg, macros.stack_ptr, offset)
                    args.append(tmp_reg)
                    
        asm_method = getattr(asm, inst_name)
        asm_method(*args)
        
        if store_back_sym:
            offset = store_back_sym.offset_from_base - self.current_stack_depth
            asm.store(macros.stack_ptr, offset, macros.t0)
            
        macros.push(rd_reg_to_push)
        self.current_stack_depth += asm.REGISTER_SIZE

    def Tuple(self, node):
        for child in node.children:
            self._compile_node(child)

    def Identifier(self, node):
        sym = self.get_symbol(node.value)
        if not sym: 
            raise ValueError(f"Undefined variable: '{node.value}' at line {node.line}:{node.col}")
        offset = (sym.offset_from_base - self.current_stack_depth) 
        asm.lw(macros.t0, macros.stack_ptr, offset) 
        macros.push(macros.t0)
        self.current_stack_depth += asm.REGISTER_SIZE

    def Value(self, node):
        macros.push_value(node.value)
        self.current_stack_depth += asm.REGISTER_SIZE

    def Deref(self, node):
        self._compile_node(node.left)
        macros.pop(macros.t0) 
        asm.lw(macros.t1, macros.t0, 0)
        macros.push(macros.t1)