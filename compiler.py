import macros
import tokens
import AST
from macros import asm
from AST import NodeType, ASTNode
from typing import Dict, List, Optional
from dataclasses import dataclass


class Workspace:
    def __init__(self):
        self.global_types = {} 
        self.global_macros = {}
        self.macro_registry = AST.MacroRegistry()
        self.loaded_files = set()

    def compile_project(self, main_filepath):
        self.discover_file(main_filepath)
        full_ast = self.semantic_parse_file(main_filepath)
        comp = Compiler()
        return comp.compile(full_ast)

    def discover_file(self, filepath):
        if filepath in self.loaded_files: 
            return
        self.loaded_files.add(filepath)

        with open(filepath, 'r') as f:
            source = f.read()
        
        token_list = tokens.tokenize(source)
        
        # Pass 1: Parse everything (no skipping) to extract Types AND Macros
        parser = AST.Parser(token_list, self.macro_registry, skip_blocks=False, type_env=self.global_types, exported_macros=self.global_macros)
        ast_skeleton = parser.parse_program()

        self._extract_signatures(ast_skeleton, filepath)

    def _extract_signatures(self, node, current_filepath, current_type=None):
        if not node: 
            return
        
        if node.node_type == NodeType.FunctionDef:
            func_name = node.value
            if func_name.startswith('.'):
                if current_type:
                    func_name = current_type + func_name
                    node.value = func_name 
            
            ret_type = node.left.type_name if node.left else None
            self.global_types[func_name] = ret_type
            
            new_type = current_type if func_name.startswith('.') else func_name
            for child in getattr(node, 'children',[]):
                self._extract_signatures(child, current_filepath, new_type)
            if getattr(node, 'left', None):
                self._extract_signatures(node.left, current_filepath, new_type)
            if getattr(node, 'right', None):
                self._extract_signatures(node.right, current_filepath, new_type)
        else:
            for child in getattr(node, 'children',[]):
                self._extract_signatures(child, current_filepath, current_type)
            if getattr(node, 'left', None):
                self._extract_signatures(node.left, current_filepath, current_type)
            if getattr(node, 'right', None):
                self._extract_signatures(node.right, current_filepath, current_type)

    def semantic_parse_file(self, filepath):
        with open(filepath, 'r') as f:
            source = f.read()
            
        token_list = tokens.tokenize(source)
        
        # Pass 2: Re-parse using the fully populated global Type and Macro state
        parser = AST.Parser(token_list, self.macro_registry, skip_blocks=False, type_env=self.global_types.copy(), exported_macros=self.global_macros)
        ast_full = parser.parse_program()
        
        self._inline_imports(ast_full)
        return ast_full

    def _inline_imports(self, node):
        if not node or not hasattr(node, 'children'): 
            return
        new_children =[]
        for child in node.children:
            if child.node_type == NodeType.Intrinsic and child.value == "import":
                path = child.children[0].value 
                imported_ast = self.semantic_parse_file(path)
                new_children.extend(imported_ast.children)
            else:
                self._inline_imports(child)
                new_children.append(child)
        node.children = new_children


@dataclass
class SymbolInfo:
    offset_from_base: int  

class Compiler:
    def __init__(self, cpu_lib=None, cpu_state_type=None):
        self.scopes: List[Dict[str, SymbolInfo]] = [{}]
        self.current_stack_depth = 0
        self.label_counter = 0
        self.function_registry = {}
        self.pure_context_out_var = None
        self.pure_context_history = []
        self.comptime_evaluator = None 

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
        self._register_functions(node)
        self._compile_node(node)
        return asm
    
    def _register_functions(self, node: ASTNode, current_type_context=None):
        if not node: 
            return
            
        if node.node_type == NodeType.FunctionDef:
            func_name = node.value
            
            if func_name.startswith(".") and current_type_context:
                func_name = current_type_context + func_name
                
            if node.left.node_type == NodeType.Identifier:
                ret_nodes = [node.left]
            elif node.left.node_type == NodeType.Tuple:
                ret_nodes = node.left.children
            else:
                ret_nodes =[]
                
            pattern_node = node.right
            
            if not pattern_node or (pattern_node.node_type == NodeType.Tuple and not pattern_node.children):
                pat_args = list()
            elif pattern_node.node_type == NodeType.Tuple:
                pat_args = pattern_node.children
            else:
                pat_args = [pattern_node]
                
            func_label = self._mangle_label(func_name, pat_args)
            
            if func_name not in self.function_registry:
                self.function_registry[func_name] = list()
                
            already_exists = any(d['label'] == func_label for d in self.function_registry[func_name])
            if not already_exists:
                body = node.children[0]
                self.function_registry[func_name].append({
                    'ret_nodes': ret_nodes,
                    'pat_args': pat_args,
                    'label': func_label,
                    'body': body,
                    'is_comptime_safe': getattr(body, 'is_pure', False), 
                })
                
            for child in getattr(node, 'children',[]):
                self._register_functions(child, func_name)
            if getattr(node, 'left', None):
                self._register_functions(node.left, func_name)
            if getattr(node, 'right', None):
                self._register_functions(node.right, func_name)
                  
        else:
            if hasattr(node, 'children') and node.children:
                for child in node.children:
                    self._register_functions(child, current_type_context)
            if getattr(node, 'left', None):
                self._register_functions(node.left, current_type_context)
            if getattr(node, 'right', None):
                self._register_functions(node.right, current_type_context)
    
    def _mangle_label(self, func_name, pat_args, line_col=None):
        parts =[func_name.replace(".", "_")]
        if line_col:
            parts.append(f"loc_{line_col[0]}_{line_col[1]}") # Unique per call-site, very cursed, don't care.
        for i, p in enumerate(pat_args):
            if p.node_type == NodeType.Value:
                parts.append(f"val{p.value}")
            else:
                parts.append(f"any{i}")
        return "_".join(parts)
    
    def _compile_node(self, node: ASTNode):
        if not node: 
            return
        method_name = node.node_type.name
        visitor = getattr(self, method_name, self.error)
        return visitor(node)
        
    def error(self, node):
        raise NotImplementedError(f"No compile method for {node.node_type} at line {node.line}:{node.col}")
    def CallerContext(self, node):
        assert hasattr(node, 'left'), "CallerContext missing left child"
        assert self.pure_context_out_var is None or isinstance(self.pure_context_out_var, str), "Invalid pure context state"

        saved_pure = self.pure_context_out_var
        popped = False
        saved_history_val = None
        
        # Step out exactly one macro context layer by popping it
        if self.pure_context_history:
            saved_history_val = self.pure_context_history.pop()
            self.pure_context_out_var = saved_history_val
            popped = True
            
        self._compile_node(node.left)
        
        # Restore the macro context layer after the block executes
        if popped:
            self.pure_context_history.append(saved_history_val)
            
        self.pure_context_out_var = saved_pure
        
    def _ast_nodes_equal(self, n1, n2):
        if n1 is None and n2 is None: return True
        if n1 is None or n2 is None: return False
        if n1.node_type != n2.node_type: return False
        if n1.value != n2.value: return False
        if len(n1.children) != len(n2.children): return False
        for c1, c2 in zip(n1.children, n2.children):
            if not self._ast_nodes_equal(c1, c2): return False
        if not self._ast_nodes_equal(n1.left, n2.left): return False
        if not self._ast_nodes_equal(n1.right, n2.right): return False
        return True

    def FunctionDef(self, node):
        func_name = node.value
        
        if func_name.startswith(".") and getattr(self, 'current_type_context', None):
            func_name = self.current_type_context + func_name

        ret_nodes = []
        if node.left.node_type == NodeType.Identifier:
            ret_nodes =[node.left]
        elif node.left.node_type == NodeType.Tuple:
            ret_nodes = node.left.children

        pattern_node = node.right
        body = node.children[0]
        
        if not pattern_node or (pattern_node.node_type == NodeType.Tuple and not pattern_node.children):
            pat_args = list()
        elif pattern_node.node_type == NodeType.Tuple:
            pat_args = pattern_node.children
        else:
            pat_args = [pattern_node]
            
        func_label = self._mangle_label(func_name, pat_args)
        
        skip_label = self.get_unique_label("skip_func")
        asm.jal(macros.x0, skip_label)
        
        asm.label(func_label)
        
        old_func_name = getattr(self, 'current_function_name', None)
        self.current_function_name = func_name
        
        old_ret_node = getattr(self, 'current_return_node', None)
        self.current_return_node = node.left
        
        self.enter_scope()
        old_stack_depth = self.current_stack_depth
        self.current_stack_depth = 0
        
        macros.push(macros.ra)
        self.current_stack_depth += asm.REGISTER_SIZE
        
        offset = -asm.REGISTER_SIZE
        for p in reversed(pat_args):
            if p.node_type == NodeType.Identifier:
                info = SymbolInfo(offset_from_base=offset)
                self.scopes[-1][p.value] = info
            offset -= asm.REGISTER_SIZE
            
        macros.push(macros.x0)
        self.current_stack_depth += asm.REGISTER_SIZE
        
        for rv in ret_nodes:
            if rv.node_type == NodeType.Identifier:
                # Check if the return variable is already bound to an argument
                if rv.value not in self.scopes[-1]:
                    macros.push(macros.x0)
                    self.current_stack_depth += asm.REGISTER_SIZE
                    self.declare_symbol(rv.value)

        # The loop target MUST be placed after all local frame initializations 
        # to prevent TRO jumps from leaking stack by re-pushing local variables.
        asm.label(func_label + "_loop")
            
        old_type_ctx = getattr(self, 'current_type_context', None)
        self.current_type_context = func_name
        
        # Save the true base stack depth of the frame for safe TRO unwinding
        old_loop_base = getattr(self, 'loop_base_depth', None)
        self.loop_base_depth = self.current_stack_depth
        
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = None
        
        self._compile_node(body)
        
        self.current_assignment_lhs = old_lhs
        self.loop_base_depth = old_loop_base
        self.current_type_context = old_type_ctx
        self.current_return_node = old_ret_node
        
        safe_regs =[18, 19, 20, 21, 22, 23, 24, 25] # s2-s9 return transport
        
        if ret_nodes:
            # Process return variables and pack them into outgoing registers
            for rv in ret_nodes:
                self._compile_node(rv)
            for i in reversed(range(len(ret_nodes))):
                macros.pop(safe_regs[i])
                self.current_stack_depth -= asm.REGISTER_SIZE
        else:
            macros.load_immediate(safe_regs[0], 0)
        
        diff = self.current_stack_depth - asm.REGISTER_SIZE
        if diff > 0:
            asm.addi(macros.stack_ptr, macros.stack_ptr, -diff)
            self.current_stack_depth = asm.REGISTER_SIZE
            
        macros.pop(macros.ra)
        self.current_stack_depth -= asm.REGISTER_SIZE
        
        asm.jalr(macros.x0, macros.ra, 0)
        
        self.current_stack_depth = old_stack_depth
        self.exit_scope()
        self.current_function_name = old_func_name
        
        asm.label(skip_label)

    def Call(self, node):
        func_name = node.value
        call_args = node.children
        
        if func_name.startswith(".") and getattr(self, 'current_type_context', None):
            func_name = self.current_type_context + func_name
            
        defs = self.function_registry.get(func_name,[])
        
        # Filter matching arity
        defs = [d for d in defs if len(d['pat_args']) == len(call_args)]
        
        if not defs:
            raise ValueError(f"No matching signature for function '{func_name}' with {len(call_args)} args at line {node.line}:{node.col}")

        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = None
        
        # Push caller args to stack
        for arg in call_args:
            self._compile_node(arg)
            
        self.current_assignment_lhs = old_lhs
            
        end_dispatch_label = self.get_unique_label("end_disp")
        match_found_statically = False
        
        is_tro = False
        if getattr(self, 'current_function_name', None) == func_name:
            ret_node = getattr(self, 'current_return_node', None)
            lhs_node = getattr(self, 'current_assignment_lhs', None)
            
            def is_empty_node(n):
                return n is None or (n.node_type == NodeType.Tuple and len(n.children) == 0)
                
            if is_empty_node(lhs_node) and is_empty_node(ret_node):
                is_tro = True
            elif lhs_node is not None and ret_node is not None:
                if self._ast_nodes_equal(lhs_node, ret_node):
                    is_tro = True
        
        for definition in defs:
            pat_args = definition['pat_args']
            next_def_label = self.get_unique_label("next_def")
            
            has_runtime_checks = False
            static_fail = False
            
            for i, p in enumerate(pat_args):
                if p.node_type == NodeType.Value:
                    # Optimize: If caller provided a literal, evaluate branch eligibility at comptime
                    if getattr(call_args[i], 'node_type', None) == NodeType.Value:
                        if call_args[i].value != p.value:
                            static_fail = True
                            break
                        else:
                            continue
                            
                    has_runtime_checks = True
                    offset_from_top = (len(call_args) - i) * asm.REGISTER_SIZE
                    asm.lw(macros.t0, macros.stack_ptr, -offset_from_top)
                    macros.load_immediate(macros.t1, p.value)
                    asm.bne(macros.t0, macros.t1, next_def_label)
                    
            if static_fail:
                continue
                
            # SUCCESS BLOCK (Branch matched)
            if is_tro:
                saved_depth = self.current_stack_depth
                
                # 1. Pop arguments right-to-left into temporary safe registers first
                # Expanding array size to safely accommodate functions with up to 15 arguments
                temp_regs =[5, 6, 7, 28, 29, 30, 31, 10, 11, 12, 13, 14, 15, 16, 17][:len(pat_args)]
                for reg in reversed(temp_regs):
                    macros.pop(reg)
                    self.current_stack_depth -= asm.REGISTER_SIZE
                
                # 2. Store them back into their unique parameter slots on the parent frame
                for i, reg in enumerate(temp_regs):
                    offset_from_base = -asm.REGISTER_SIZE * (len(temp_regs) - i)
                    offset = offset_from_base - self.current_stack_depth
                    asm.store(macros.stack_ptr, offset, reg)
                    
                # Calculate difference to the true loop frame base, NOT a hardcoded 4 bytes
                diff = self.current_stack_depth - getattr(self, 'loop_base_depth', asm.REGISTER_SIZE)
                if diff > 0:
                    asm.addi(macros.stack_ptr, macros.stack_ptr, -diff)
                    
                asm.jal(macros.x0, definition['label'] + "_loop")
                self.current_stack_depth = saved_depth
            else:
                asm.jal(macros.ra, definition['label'])
                asm.jal(macros.x0, end_dispatch_label)
                
            asm.label(next_def_label)
            
            if not has_runtime_checks:
                match_found_statically = True
                break
                
        if not match_found_statically:
            asm.ecall() # Traps if no pattern fell through successfully
            
        asm.label(end_dispatch_label)
        
        num_returns = len(defs[0]['ret_nodes']) if defs else 1
        safe_regs =[18, 19, 20, 21, 22, 23, 24, 25]

        if is_tro:
            self.current_stack_depth -= (len(call_args) * asm.REGISTER_SIZE)
            for _ in range(num_returns if num_returns > 0 else 1):
                macros.push(macros.x0) 
                self.current_stack_depth += asm.REGISTER_SIZE
        else:
            # Caller cleanly pops the evaluated arguments it created originally
            num_args = len(call_args)
            if num_args > 0:
                asm.addi(macros.stack_ptr, macros.stack_ptr, -(num_args * asm.REGISTER_SIZE))
                self.current_stack_depth -= (num_args * asm.REGISTER_SIZE)
            
            # Retrieve callee's returned result left in registers and push them onto the stack
            if num_returns > 0:
                for i in range(num_returns):
                    macros.push(safe_regs[i])
                    self.current_stack_depth += asm.REGISTER_SIZE
            else:
                macros.push(safe_regs[0])
                self.current_stack_depth += asm.REGISTER_SIZE

    def Assignment(self, node):
        assert self.pure_context_out_var is None or isinstance(self.pure_context_out_var, str), "Invalid pure context state in Assignment"
        
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = node.left

        if self.pure_context_out_var is not None:
            if node.left.node_type == NodeType.Identifier:
                if node.left.value != self.pure_context_out_var:
                    raise SyntaxError(f"Visible Mutation Guarantee Violation at {node.line}:{node.col} -> Pure macro cannot mutate external variable '{node.left.value}'")
            elif node.left.node_type == NodeType.Deref:
                raise SyntaxError(f"Visible Mutation Guarantee Violation at {node.line}:{node.col} -> Pure macro cannot mutate memory via pointer Deref")

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
            self.current_assignment_lhs = None
            self._compile_node(node.left.left)
            self.current_assignment_lhs = node.left
            
            self._compile_node(node.right)
            
            macros.pop(macros.t0)
            self.current_stack_depth -= asm.REGISTER_SIZE
            macros.pop(macros.t1)
            self.current_stack_depth -= asm.REGISTER_SIZE
            
            asm.store(macros.t1, 0, macros.t0)
            
        elif node.left.node_type == NodeType.Tuple:
            self._compile_node(node.right)
            
            num_targets = len(node.left.children)
            safe_regs =[18, 19, 20, 21, 22, 23, 24, 25] # s2-s9 (Safe non-volatile storage from clobbering)
            
            # Pop all RHS evaluated values right-to-left into safe registers to free up the stack
            for i in reversed(range(num_targets)):
                macros.pop(safe_regs[i])
                self.current_stack_depth -= asm.REGISTER_SIZE
                
            for i, target in enumerate(node.left.children):
                if target.node_type == NodeType.Identifier:
                    target_name = target.value
                    if target_name and target_name.startswith(".") and getattr(self, 'current_type_context', None):
                        target_name = self.current_type_context + target_name
                        
                    sym = self.get_symbol(target_name)
                    if sym:
                        offset = sym.offset_from_base - self.current_stack_depth
                        asm.store(macros.stack_ptr, offset, safe_regs[i])
                    else:
                        macros.push(safe_regs[i])
                        self.current_stack_depth += asm.REGISTER_SIZE
                        self.declare_symbol(target_name)
                        
                elif target.node_type == NodeType.Deref:
                    # Protect RHS values in safe_regs from being clobbered by target.left evaluation
                    for r in range(num_targets):
                        macros.push(safe_regs[r])
                        self.current_stack_depth += asm.REGISTER_SIZE
                    
                    # Compile pointer expression (safely pushes to freed stack space)
                    self.current_assignment_lhs = None
                    self._compile_node(target.left)
                    self.current_assignment_lhs = node.left
                    
                    # Pop pointer
                    macros.pop(macros.t1)
                    self.current_stack_depth -= asm.REGISTER_SIZE
                    
                    # Restore RHS values
                    for r in reversed(range(num_targets)):
                        macros.pop(safe_regs[r])
                        self.current_stack_depth -= asm.REGISTER_SIZE
                    
                    # Store unpacked value directly at the pointer
                    asm.store(macros.t1, 0, safe_regs[i])
        else:
            raise SyntaxError(f"Syntax Error at line {node.line}:{node.col} -> Invalid assignment target {node.left.node_type.name}")
            
        self.current_assignment_lhs = old_lhs

    def Block(self, node):
        self.enter_scope()
        start_depth = self.current_stack_depth
        
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        
        for i, child in enumerate(node.children):
            if i < len(node.children) - 1:
                self.current_assignment_lhs = None
            else:
                self.current_assignment_lhs = old_lhs
                
            self._compile_node(child)
            
        self.current_assignment_lhs = old_lhs
        
        diff = self.current_stack_depth - start_depth
        if diff > 0:
            asm.addi(macros.stack_ptr, macros.stack_ptr, -diff)
            self.current_stack_depth = start_depth
        self.exit_scope()

    def MacroCall(self, node):
        self.enter_scope()
        
        start_depth = self.current_stack_depth
        
        old_pure_out_var = self.pure_context_out_var
        self.pure_context_history.append(old_pure_out_var)
        
        if node.is_pure:
            assert isinstance(node.value, str)
            self.pure_context_out_var = node.value 
        elif old_pure_out_var is not None:
            raise SyntaxError(f"VMG Violation at {node.line}:{node.col}")

        macros.push(macros.x0)
        self.current_stack_depth += asm.REGISTER_SIZE
        out_sym = self.declare_symbol(node.value)
        
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = None
        
        self._compile_node(node.left)
        
        self.current_assignment_lhs = old_lhs
        
        self.pure_context_out_var = old_pure_out_var
        self.pure_context_history.pop()

        offset = out_sym.offset_from_base - self.current_stack_depth
        asm.lw(macros.t0, macros.stack_ptr, offset)
        self.exit_scope()

        diff = self.current_stack_depth - start_depth
        if diff > 0:
            asm.addi(macros.stack_ptr, macros.stack_ptr, -diff)
            self.current_stack_depth = start_depth

        macros.push(macros.t0)
        self.current_stack_depth += asm.REGISTER_SIZE

    def Program(self, node):
        for child in node.children:
            self._compile_node(child)
        asm.ecall()


    def MacroDef(self, node):
        pass

    def Pipeline(self, node):
        self._compile_node(node.left)
        if node.right:
            self._compile_node(node.right)

    def Intrinsic(self, node):
        if node.value == "asm":
            self._compile_asm(node)
        elif node.value == "embed":
            self._compile_embed(node)

    def _compile_embed(self, node):
        path = node.children[0].value
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

    def _compile_asm(self, node):
        inst_name = node.children[0].value

        if self.pure_context_out_var is not None:
            if inst_name in {"store", "sw", "sb"}:
                raise SyntaxError(f"Visible Mutation Guarantee Violation at {node.line}:{node.col} -> Pure macro cannot use globally mutating instruction '{inst_name}'")

        args = list()
        reg_map = macros.reg_map
        no_rd_instructions = macros.no_rd_instructions
        imm_positions = macros.imm_positions
        has_rd = inst_name not in no_rd_instructions
        
        temp_pool =[ 6, 7, 28, 29, 30, 31 ] 
        temp_idx = 0
        store_back_sym = None
        rd_reg_to_push = 0
        
        eval_args = []
        
        # Phase 1: Categorize arguments
        for i, arg in enumerate(node.children[1:]):
            
            # Check for branching labels
            if inst_name in {"jal", "bge", "beq", "bne", "label"} and i == len(node.children[1:]) - 1:
                eval_args.append({'type': 'literal', 'val': arg.value if hasattr(arg, 'value') else arg})
                continue

            # Check for immediates
            if inst_name in imm_positions and i in imm_positions[inst_name]:
                if getattr(arg, 'node_type', None) == NodeType.Value:
                    eval_args.append({'type': 'literal', 'val': arg.value})
                else:
                    eval_args.append({'type': 'literal', 'val': getattr(arg, 'value', arg)})
                continue

            # Strip CallerContext wrapper to inspect the raw argument
            arg_eval = arg
            while getattr(arg_eval, 'node_type', None) == NodeType.CallerContext:
                arg_eval = arg_eval.left

            name = getattr(arg_eval, 'value', None)
            is_output = (i == 0 and has_rd)
            
            # Check for direct register usage (e.g., 'zero', 'ra')
            if isinstance(name, str) and name in reg_map:
                eval_args.append({'type': 'literal', 'val': reg_map[name]})
                if is_output:
                    rd_reg_to_push = reg_map[name]
                continue
                
            # Handle output register allocation (l-value)
            if is_output:
                if not isinstance(name, str):
                    raise ValueError(f"Output of @asm must be an identifier, got {arg_eval.node_type}")
                sym = self.get_symbol(name)
                if not sym:
                    macros.push(macros.x0)
                    self.current_stack_depth += asm.REGISTER_SIZE
                    sym = self.declare_symbol(name)
                    
                eval_args.append({'type': 'reg', 'val': 5}) # macros.t0
                store_back_sym = sym
                rd_reg_to_push = 5
            else:
                # Input argument - schedule for evaluation
                eval_args.append({'type': 'eval', 'node': arg})

        # Phase 2: Compile inputs sequentially to the stack (prevents clobbering)
        eval_nodes =[e for e in eval_args if e['type'] == 'eval']
        for e in eval_nodes:
            self._compile_node(e['node'])
            
        # Phase 3: Pop evaluated results into temporary registers in reverse order
        for e in reversed(eval_nodes):
            tmp_reg = temp_pool[temp_idx]
            temp_idx += 1
            macros.pop(tmp_reg)
            self.current_stack_depth -= asm.REGISTER_SIZE
            e['reg'] = tmp_reg
            
        # Phase 4: Construct final argument list
        for e in eval_args:
            if e['type'] == 'eval':
                args.append(e['reg'])
            elif e['type'] == 'reg':
                args.append(e['val'])
            else:
                args.append(e['val'])
                
        # Phase 5: Emit Instruction
        asm_method = getattr(asm, inst_name)
        asm_method(*args)
        
        # Phase 6: Store output back to memory frame and push to stack for caller
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
            if node.type_name:
                macros.push(macros.x0)
                self.current_stack_depth += asm.REGISTER_SIZE
                sym = self.declare_symbol(node.value)
                return
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
