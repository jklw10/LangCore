import platform
import tokens
import AST
from AST import NodeType, ASTNode
from typing import Dict, List, Optional
from dataclasses import dataclass
import ctypes


def is_body_pure(self) -> bool:
    """Return True if the AST subtree contains no visible mutation."""
    if self is None:
        return True
    if self.node_type == NodeType.Assignment:
        if getattr(self.left, 'node_type', None) == NodeType.Lens and self.left.left is None:
            return False
    if self.node_type == NodeType.Intrinsic and self.value == "asm":
        if self.children and platform.is_mutating_instruction(self.children[0].value): 
            return False
    
    for child in getattr(self, 'children', []):
        if isinstance(child, ASTNode) and not child.is_body_pure():
            return False
    if getattr(self, 'left', None) and isinstance(self.left, ASTNode) and not self.left.is_body_pure():
        return False
    if getattr(self, 'right', None) and isinstance(self.right, ASTNode) and not self.right.is_body_pure():
        return False
    return True

class ComptimeFolder:
    def __init__(self, cpu_lib, cpu_state_type, full_ast):
        self.lib = cpu_lib
        self.RiscVState = cpu_state_type
        self.functions = self.extract_functions(full_ast)
        
    def extract_functions(self, node):
        funcs = []
        if not node: 
            return funcs
        if node.node_type == NodeType.Definition:
            funcs.append(node)
        for child in getattr(node, 'children', []):
            funcs.extend(self.extract_functions(child))
        if getattr(node, 'left', None): funcs.extend(self.extract_functions(node.left))
        if getattr(node, 'right', None): funcs.extend(self.extract_functions(node.right))
        return funcs

    def evaluate_node(self, node):
        # Reset the platform for micro-compilation
        platform.init()
        platform.asm.code = bytearray()
        platform.asm.labels = {}
        platform.asm.fixups = {}
        platform.asm.pc = 0
        
        # Jump over function definitions
        platform.jump("comptime_main")
        
        temp_comp = Compiler()
        for f in self.functions:
            temp_comp._register_functions(f)
            
        for f in self.functions:
            temp_comp._compile_node(f)
            
        platform.label("comptime_main")
        platform.emit_instruction("addi", platform.get_register("fp"), platform.get_register("sp"), 0)
        
        # Micro-compile the isolated node
        platform.start_scope()
        temp_comp._compile_node(node)
        platform.end_scope(returns=1)
        
        platform.pop(platform.get_register("a0"))
        platform.halt()
        
        bin_data = platform.get_binary()
        
        # Run Native CPU Emulator Sandbox
        cpu = self.RiscVState()
        self.lib.init_cpu(ctypes.byref(cpu))
        for i, b in enumerate(bin_data):
            cpu.memory[i] = b
            
        cycles = 0
        while not cpu.halt and cycles < 50000:
            self.lib.run_cycles(ctypes.byref(cpu), 1)
            cycles += 1
            
        if cycles >= 50000:
            raise TimeoutError("Comptime execution exceeded max cycle limit")
            
        val = cpu.regs[10]
        # Standardize 32-bit uint back to signed integer format for the AST
        if val >= 0x80000000:
            val -= 0x100000000
        return val

    def has_only_static_caller_contexts(self, n):
        if not n: 
            return True
        
        # If it's a hygiene-substituted node, it must resolve to a raw Value
        if getattr(n, 'caller_context_depth', 0) > 0:
            if n.node_type != NodeType.Value: 
                return False
            return True 
            
        for c in getattr(n, 'children', []): 
            if not self.has_only_static_caller_contexts(c): return False
        if getattr(n, 'left', None) and not self.has_only_static_caller_contexts(n.left): return False
        if getattr(n, 'right', None) and not self.has_only_static_caller_contexts(n.right): return False
        return True

    def fold(self, node: ASTNode):
        if not node: return
        
        for child in getattr(node, 'children', []): self.fold(child)
        if getattr(node, 'left', None): self.fold(node.left)
        if getattr(node, 'right', None): self.fold(node.right)
        
        if node.node_type == NodeType.Call:
            if all(getattr(c, 'node_type', None) == NodeType.Value for c in node.children):
                is_pure = False
                for f in self.functions:
                    if f.value == node.value and f.children[0].is_body_pure():
                        is_pure = True
                        break
                if is_pure:
                    try:
                        val = self.evaluate_node(node)
                        if val is not None:
                            node.node_type = NodeType.Value
                            node.value = val
                            node.children = []
                            node.left = None
                            node.right = None
                    except Exception:
                        pass
                        
        if getattr(node, 'vmg_pure_out_target', None) and getattr(node, 'is_pure', False):
            if self.has_only_static_caller_contexts(node):
                try:
                    val = self.evaluate_node(node)
                    if val is not None:
                        node.node_type = NodeType.Value
                        node.value = val
                        node.children = []
                        node.left = None
                        node.right = None
                        node.vmg_pure_out_target = None # Prevent compiler wrapping it again
                except Exception:
                    pass

class Workspace:
    def __init__(self, cpu_lib=None, cpu_state_type=None):
        self.global_types = {} 
        self.global_macros = {}
        self.macro_registry = AST.MacroRegistry()
        self.loaded_files = set()
        self.cpu_lib = cpu_lib
        self.cpu_state_type = cpu_state_type

    def compile_project(self, main_filepath):
        assert isinstance(main_filepath, str) and main_filepath, "Project entry point must be a valid, non-empty file path string"
        
        self.discover_file(main_filepath)
        full_ast = self.semantic_parse_file(main_filepath)
        
        assert full_ast.node_type == NodeType.Block, "Compilation structural entry point must be a Block node"
        
        # JIT COMPTIME FOLD PASS
        if self.cpu_lib and self.cpu_state_type:
            folder = ComptimeFolder(self.cpu_lib, self.cpu_state_type, full_ast)
            folder.fold(full_ast)
        
        # Reset platform explicitly after Comptime micro-compilations finish
        platform.init()
        platform.asm.code = bytearray()
        platform.asm.labels = {}
        platform.asm.fixups = {}
        platform.asm.pc = 0

        comp = Compiler()
        result_platform = comp.compile(full_ast)
        
        assert hasattr(result_platform, 'get_code_length') and result_platform.get_code_length() > 0, "Compilation critically output zero executable machine code instructions"
        return result_platform

    def discover_file(self, filepath):
        assert isinstance(filepath, str), "Filepath must be processed as a strict string type"
        
        if filepath in self.loaded_files: 
            return
        self.loaded_files.add(filepath)

        with open(filepath, 'r') as f:
            source = f.read()
        
        token_list = tokens.tokenize(source)
        
        parser = AST.Parser(token_list, self.macro_registry, skip_blocks=False, type_env=self.global_types, exported_macros=self.global_macros, import_callback=self.discover_file)
        ast_skeleton = parser.parse_program()
        
        assert ast_skeleton is not None, f"Lexical parser failed to generate a valid AST skeleton for {filepath}"
        self._extract_signatures(ast_skeleton, filepath)

    def _extract_signatures(self, node, current_filepath, current_type=None):
        if not node: 
            return
            
        if node.node_type == NodeType.Intrinsic and node.value == "import":
            assert len(node.children) == 1, "Import intrinsic explicitly requires exactly one path parameter argument"
            assert isinstance(node.children[0].value, str) and node.children[0].value, "Import logically mandates structurally defined path literal string mapping external logic sources"
            self.discover_file(node.children[0].value)
            return
            
        if node.node_type == NodeType.Definition:
            assert isinstance(node.value, str) and node.value, "Function definition must possess a structural name string"
            
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
        assert filepath in self.loaded_files, f"Cannot semantic parse un-discovered file: {filepath}"
        
        with open(filepath, 'r') as f:
            source = f.read()
            
        token_list = tokens.tokenize(source)
        
        parser = AST.Parser(token_list, self.macro_registry, skip_blocks=False, type_env=self.global_types.copy(), exported_macros=self.global_macros, import_callback=None)
        ast_full = parser.parse_program()
        
        assert ast_full is not None, "Semantic parser failed to construct a final AST framework"
        self._inline_imports(ast_full)
        
        assert ast_full.node_type == NodeType.Block, "Semantic parse routine must definitively yield a Block root node"
        return ast_full

    def _inline_imports(self, node):
        if not node or not hasattr(node, 'children'): 
            return
        
        new_children =[]
        for child in node.children:
            if child.node_type == NodeType.Intrinsic and child.value == "import":
                assert len(child.children) == 1, "Import intrinsic explicitly requires exactly one path parameter argument"
                path = child.children[0].value 
                
                imported_ast = self.semantic_parse_file(path)
                assert imported_ast is not None and hasattr(imported_ast, 'children'), "Imported library AST structure is critically malformed"
                
                new_children.extend(imported_ast.children)
            else:
                self._inline_imports(child)
                new_children.append(child)
                
        node.children = new_children


@dataclass
class SymbolInfo:
    fp_offset: int  

class Compiler:
    def __init__(self, cpu_lib=None, cpu_state_type=None):
        self.scopes: List[Dict[str, SymbolInfo]] = [{}]
        self.label_counter = 0
        self.function_registry = {}
        self.pure_context_out_var = None
        self.pure_context_history = []
        self.comptime_evaluator = None 
        self.macro_expansion_counter = 0
        self.macro_expansion_stack = []
        self.local_fp_offset = 0
        self.loop_base_fp_offset = 0
        self.tco_triggered_in_expression = False

    def enter_scope(self):
        assert isinstance(self.scopes, list), "Scope stack framework lost structural integrity"
        self.scopes.append({})

    def exit_scope(self):
        assert len(self.scopes) > 1, "CRITICAL: Cannot forcefully exit the global top-level runtime scope layer"
        self.scopes.pop()

    def get_unique_label(self, prefix="lbl"):
        assert isinstance(prefix, str) and prefix, "Label prefix request must be a valid non-empty string"
        self.label_counter += 1
        label = f"{prefix}_{self.label_counter}"
        return label

    def compile(self, node: ASTNode):
        platform.init()
        self._register_functions(node)
        #TODO: check if file name should be injected here or smth
        self.current_type_context = getattr(self, 'current_type_context', "main")
        
        platform.emit_instruction("addi", platform.get_register("fp"), platform.get_register("sp"), 0)
        
        platform.start_scope()
        self._compile_statement_sequence(node.children)
        platform.end_scope(returns=0)
        
        platform.halt()
        assert len(self.scopes) == 1, f"Compiler execution leaked {len(self.scopes) - 1} un-exited scope layers upon finish"
        return platform
    
    def Block(self, node):
        start_fp_offset = getattr(self, 'local_fp_offset', 0)
        
        platform.start_scope()
        self.enter_scope()
        
        self._compile_statement_sequence(node.children)
        
        self.exit_scope()
        platform.end_scope(returns=0)

        self.local_fp_offset = start_fp_offset

    def _register_functions(self, node: ASTNode, current_type_context=None):
        if not node: 
            return
        
        if node.node_type == NodeType.Definition:
            func_name = node.value
            
            if func_name.startswith(".") and current_type_context:
                func_name = current_type_context + func_name
                
            if node.left.node_type == NodeType.Identifier:
                ret_nodes =[node.left]
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
            parts.append(f"loc_{line_col[0]}_{line_col[1]}") 
        for i, p in enumerate(pat_args):
            if p.node_type == NodeType.Value:
                parts.append(f"val{p.value}")
            else:
                parts.append(f"any{i}")
        label = "_".join(parts)
        return label
    
    def _compile_node(self, node: ASTNode):
        if not node: 
            return
            
        depth = getattr(node, 'caller_context_depth', 0)
        popped_states = []
        
        # Winding Down (Restoring Caller context)
        if depth > 0:
            for _ in range(depth):
                if self.pure_context_history:
                    popped_states.append(self.pure_context_out_var)
                    self.pure_context_out_var = self.pure_context_history.pop()

        # --- THE MACRO HARDWARE WRAPPER ---
        has_vmg = getattr(node, 'vmg_pure_out_target', None) is not None
        if has_vmg:
            self.macro_expansion_counter += 1
            self.macro_expansion_stack.append(self.macro_expansion_counter)
            
            self.enter_scope()
            platform.start_scope()
            start_fp_offset = getattr(self, 'local_fp_offset', 0)
            
            old_pure_out_var = self.pure_context_out_var
            self.pure_context_history.append(old_pure_out_var)
            self.pure_context_out_var = node.vmg_pure_out_target
            
            # Physically allocate the output slot for the macro
            platform.push(platform.x0)
            out_sym = self.declare_symbol(node.vmg_pure_out_target)

            old_lhs = getattr(self, 'current_assignment_lhs', None)
            self.current_assignment_lhs = None

        # Execute the unrolled node
        method_name = node.node_type.name
        visitor = getattr(self, method_name, self.error)
        result = visitor(node)

        # --- EXTRACT THE MACRO RESULT ---
        if has_vmg:
            self.current_assignment_lhs = old_lhs
            
            # Extract the calculated value from local memory
            platform.read_local(platform.t0, out_sym.fp_offset, node.vmg_pure_out_target)
            self.exit_scope()
            platform.end_scope(returns=0)
            self.local_fp_offset = start_fp_offset
            
            self.pure_context_history.pop()
            self.pure_context_out_var = old_pure_out_var
            
            self.macro_expansion_stack.pop()
            
            # Push it so the parent Assignment receives exactly 1 item!
            platform.push(platform.t0)

        # Winding Up (Restoring Macro context)
        if depth > 0:
            for saved_out_var in reversed(popped_states):
                self.pure_context_history.append(self.pure_context_out_var)
                self.pure_context_out_var = saved_out_var
                
        return result
      
    def _ast_nodes_equal(self, n1, n2):
        if n1 is None and n2 is None:       return True
        if n1 is None or n2 is None:        return False
        
        if n1.node_type != n2.node_type:    return False
        if n1.value != n2.value:            return False
        if len(n1.children) != len(n2.children):    return False
        for c1, c2 in zip(n1.children, n2.children):
            if not self._ast_nodes_equal(c1, c2):           return False
        if not self._ast_nodes_equal(n1.left, n2.left):     return False
        if not self._ast_nodes_equal(n1.right, n2.right):   return False
        return True
    
    def error(self, node):
        raise NotImplementedError(f"CRITICAL: Unmapped evaluation method for AST structure {node.node_type} at line {node.line}:{node.col}")
    
    def get_symbol(self, name: str) -> Optional[SymbolInfo]:
        for scope in reversed(self.scopes):
            if name in scope:
                sym = scope[name]
                return sym
        return None

    def declare_symbol(self, name: str):
        assert isinstance(name, str) and name
        assert len(self.scopes) > 0, "Local layer assignment invariant violated: No active scope exists"
        assert name not in self.scopes[-1], f"Local variable '{name}' overlaps an already defined footprint in the active scope layer"
        
        info = SymbolInfo(fp_offset=self.local_fp_offset)
        self.scopes[-1][name] = info
        self.local_fp_offset += 1
        return info

    def Identifier(self, node):
        name = node.value
        if name.startswith(".") and getattr(self, 'current_type_context', None):
            name = self.current_type_context + name

        if hasattr(self, 'static_fields') and name in self.static_fields:
            val = self.static_fields[name]
            if isinstance(val, str):
                data = val.encode('utf-8')
                skip_label = self.get_unique_label("skip_str")
                platform.jump_and_link(platform.t0, skip_label)
                platform.emit_aligned_bytes(data)
                platform.label(skip_label)
                
                platform.push(platform.t0)
                platform.push_value(len(data))
            else:
                platform.push_value(val)
            return

        sym = self.get_symbol(node.value)
        if not sym: 
            if node.type_name:
                platform.push(platform.x0)
                sym = self.declare_symbol(node.value)
                return
            raise ValueError(f"Undefined variable footprint lookup: '{node.value}' at line {node.line}:{node.col}")
            
        platform.read_local(platform.t0, sym.fp_offset, node.value) 
        platform.push(platform.t0)

    def Definition(self, node):
        func_name = node.value
        if func_name.startswith(".") and getattr(self, 'current_type_context', None):
            func_name = self.current_type_context + func_name

        ret_nodes =[]
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
            pat_args =[pattern_node]
            
        func_label = self._mangle_label(func_name, pat_args)
        
        skip_label = self.get_unique_label("skip_func")
        platform.jump(skip_label)
        
        platform.label(func_label)
        
        old_func_name = getattr(self, 'current_function_name', None)
        self.current_function_name = func_name
        
        old_ret_node = getattr(self, 'current_return_node', None)
        self.current_return_node = node.left
        
        # Track argument signature length to strictly protect overloaded target footprinting 
        old_args_len = getattr(self, 'current_function_args_len', -1)
        self.current_function_args_len = len(pat_args)
        
        self.enter_scope()
        old_local_fp_offset = getattr(self, 'local_fp_offset', 0)
        
        # PROLOGUE
        platform.push(platform.ra)
        platform.push(platform.get_register("fp"))
        platform.emit_instruction("addi", platform.get_register("fp"), platform.get_register("sp"), 0)
        
        platform.start_scope()
        
        # Map Arguments (Above FP)
        arg_offset = -(2 + len(pat_args))
        for p in pat_args:
            p_name = None
            if p.node_type == NodeType.Identifier:
                p_name = p.value
            elif p.node_type == NodeType.Lens:
                p_name = p.left.value
            
            if p_name is not None:
                self.scopes[-1][p_name] = SymbolInfo(fp_offset=arg_offset)
            arg_offset += 1
        
        self.local_fp_offset = 0
        
        platform.push(platform.x0)
        self.local_fp_offset += 1
        
        for rv in ret_nodes:
            if rv.node_type == NodeType.Identifier:
                if rv.value not in self.scopes[-1]:
                    platform.push(platform.x0)
                    self.declare_symbol(rv.value)

        self.loop_base_fp_offset = self.local_fp_offset

        platform.label(func_label + "_loop")
            
        old_type_ctx = getattr(self, 'current_type_context', None)
        self.current_type_context = func_name
        
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = None
        
        self._compile_node(body)
        
        self.current_assignment_lhs = old_lhs
        self.current_type_context = old_type_ctx
        self.current_return_node = old_ret_node
        
        safe_regs = platform.get_safe_regs()
        
        if ret_nodes:
            #TODO: stackbleed.
            assert len(ret_nodes) <= len(safe_regs), f"Function {func_name} exceeds maximum allowed return values ({len(safe_regs)})"

            for i, rv in enumerate(ret_nodes):
                if rv.node_type == NodeType.Identifier:
                    sym = self.get_symbol(rv.value)
                    platform.read_local(safe_regs[i], sym.fp_offset, node.value)
                else:
                    self._compile_node(rv)
                    platform.pop(safe_regs[i])
        else:
            platform.load_immediate(safe_regs[0], 0)
            
        platform.end_scope(returns=0)
        
        # EPILOGUE
        platform.emit_instruction("addi", platform.get_register("sp"), platform.get_register("fp"), 0)
        platform.pop(platform.get_register("fp"))
        platform.pop(platform.ra)
        
        platform.return_jump()
        
        self.local_fp_offset = old_local_fp_offset
        self.exit_scope()
        
        self.current_function_name = old_func_name
        self.current_function_args_len = old_args_len
        
        platform.label(skip_label)


    def Call(self, node):
        func_name = node.value
        call_args = node.children
        
        if func_name.startswith(".") and getattr(self, 'current_type_context', None):
            func_name = self.current_type_context + func_name
            
        defs = self.function_registry.get(func_name, [])
        defs = [d for d in defs if len(d['pat_args']) == len(call_args)]
        
        if not defs:
            raise ValueError(f"No matching overloaded signature configuration found for branch '{func_name}' at line {node.line}:{node.col}")

        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = None
        
        platform.start_scope()
        
        for arg in call_args:
            self._compile_node(arg)
            
        self.current_assignment_lhs = old_lhs
        actual_args_on_stack = len(call_args)
            
        end_dispatch_label = self.get_unique_label("end_disp")
        match_found_statically = False
        
        # Arity guard required to prevent overloads from trampling stack variables if TCO replaces parameters!
        is_tro = False
        if getattr(self, 'current_function_name', None) == func_name:
            ret_node = getattr(self, 'current_return_node', None)
            lhs_node = getattr(self, 'current_assignment_lhs', None)
            
            def is_empty_node(n):
                return n is None or (n.node_type == NodeType.Tuple and len(n.children) == 0)
                
            if is_empty_node(lhs_node) and is_empty_node(ret_node):
                if actual_args_on_stack == getattr(self, 'current_function_args_len', -1):
                    is_tro = True
            elif lhs_node is not None and ret_node is not None:
                if self._ast_nodes_equal(lhs_node, ret_node):
                    if actual_args_on_stack == getattr(self, 'current_function_args_len', -1):
                        is_tro = True
        
        for definition in defs:
            pat_args = definition['pat_args']
            next_def_label = self.get_unique_label("next_def")
            
            has_runtime_checks = False
            static_fail = False
            
            for i, p in enumerate(pat_args):
                if p.node_type == NodeType.Value:
                    if getattr(call_args[i], 'node_type', None) == NodeType.Value:
                        if call_args[i].value != p.value:
                            static_fail = True
                            break
                        else:
                            continue
                            
                    has_runtime_checks = True
                    offset_from_top = len(call_args) - i
                    
                    platform.read_relative(platform.t0, -offset_from_top)
                    platform.load_immediate(platform.t1, p.value)
                    platform.branch_not_equal(platform.t0, platform.t1, next_def_label)
                    
            if static_fail:
                continue
               
            if is_tro:
                temp_regs = platform.get_temp_regs_for_tco(actual_args_on_stack)
                #TODO: bleed to stack.
                assert len(temp_regs) == actual_args_on_stack, f"Hardware limitation: TCO requires {actual_args_on_stack} temp registers, but only {len(temp_regs)} are safely available."
                for reg in reversed(temp_regs):
                    platform.pop(reg)
                    
                for i, reg in enumerate(temp_regs):
                    target_offset = -(2 + len(pat_args)) + (i + (len(pat_args) - actual_args_on_stack))
                    platform.write_local(target_offset, reg, node.value)
                    
                offset_bytes = getattr(self, 'loop_base_fp_offset', 0) * platform.REGISTER_SIZE
                platform.emit_instruction("addi", platform.get_register("sp"), platform.get_register("fp"), offset_bytes)
                    
                platform.jump(definition['label'] + "_loop")
                
                platform.compile_time_adjust_stack(actual_args_on_stack)
                self.tco_triggered_in_expression = True
            else:
                platform.call(definition['label'])
                platform.jump(end_dispatch_label)
                
            platform.label(next_def_label)
            
            if not has_runtime_checks:
                match_found_statically = True
                break
                
        if not match_found_statically:
            #TODO: should this just be an assert?
            platform.halt()
            
        platform.label(end_dispatch_label)
        
        num_returns = len(defs[0]['ret_nodes']) if defs else 1
        safe_regs = platform.get_safe_regs()
        #TODO: bleed to stack.
        assert num_returns <= len(safe_regs), "Too many return values for safe register extraction during Call"
        if is_tro:
            platform.abandon_scope()
        else:
            push_count = num_returns if num_returns > 0 else 1
            for i in range(push_count):
                platform.push(safe_regs[i])
            platform.end_scope(returns=push_count)

    def Lens(self, node):
        platform.start_scope()
        
        if node.left is None:
            self._compile_node(node.right)
            platform.pop(platform.t0) 
            platform.load_deref(platform.t1, platform.t0)
            platform.push(platform.t1)
            platform.end_scope(returns=1)
        else:
            self._compile_node(node.left)
            pushed_base_slots = platform.get_scope_pushed()

            total_elements = pushed_base_slots
            inner = node.right
            
            if inner.node_type == NodeType.Value:
                start_idx = inner.value
                end_idx = inner.value
            elif inner.node_type == NodeType.Pipeline:
                start_idx = inner.left.value
                end_idx = inner.right.value
            else:
                raise NotImplementedError("Dynamic slice bounds requiring runtime logic not yet implemented")

            if end_idx == -1: 
                end_idx = total_elements - 1

            elements_to_keep = (end_idx - start_idx) + 1
            temp_regs = platform.get_temp_regs_for_tco(elements_to_keep)
            
            for i in range(elements_to_keep):
                offset_from_top = pushed_base_slots - (start_idx + i)
                platform.read_relative(temp_regs[i], -offset_from_top)
            
            for i in range(elements_to_keep):
                platform.push(temp_regs[i])
                
            platform.end_scope(returns=elements_to_keep)

    def Assignment(self, node):
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = node.left

        if self.pure_context_out_var is not None:
            if node.left.node_type == NodeType.Identifier:
                assert node.left.value == self.pure_context_out_var, f"Visible Mutation Guarantee Violation at {node.line}:{node.col}"
            elif node.left.node_type == NodeType.Lens and node.left.left is None:
                raise SyntaxError(f"Visible Mutation Guarantee Violation at {node.line}:{node.col}")

        if node.left.node_type == NodeType.Identifier:
            name = node.left.value
            
            if name and name.startswith(".") and getattr(self, 'current_type_context', None):
                name = self.current_type_context + name
                node.left.value = name
                
                if not hasattr(self, 'static_fields'):
                    self.static_fields = {}
                    
                rhs_node = node.right
                if getattr(rhs_node, 'node_type', None) == NodeType.Call and rhs_node.value == self.current_type_context:
                    rhs_node = rhs_node.children[0]
                    
                if getattr(rhs_node, 'node_type', None) == NodeType.Value:
                    self.static_fields[name] = rhs_node.value
                    self.current_assignment_lhs = old_lhs
                    return
                
            platform.start_scope()
            self._compile_node(node.right)
            
            if getattr(self, 'tco_triggered_in_expression', False):
                self.tco_triggered_in_expression = False
                self.current_assignment_lhs = old_lhs
                platform.abandon_scope()
                return
            
            platform.end_scope(returns=1)
            
            sym = self.get_symbol(name)
            if sym:
                platform.pop(platform.t0)
                platform.write_local(sym.fp_offset, platform.t0, node.value)
            else:
                platform.peek(platform.t0)
                sym = self.declare_symbol(name)
                platform.write_local(sym.fp_offset, platform.t0, node.value)

        elif node.left.node_type == NodeType.Lens and node.left.left is None:
            self.current_assignment_lhs = None
            platform.start_scope()
            self._compile_node(node.left.right)
            self.current_assignment_lhs = node.left
            self._compile_node(node.right)
            
            if getattr(self, 'tco_triggered_in_expression', False):
                self.tco_triggered_in_expression = False
                self.current_assignment_lhs = old_lhs
                platform.abandon_scope()
                return
                
            platform.end_scope(returns=2)
            platform.pop(platform.t0)
            platform.pop(platform.t1)
            platform.store_deref(platform.t1, platform.t0)
            
        elif node.left.node_type == NodeType.Tuple:
            platform.start_scope()
            self._compile_node(node.right)
            
            if getattr(self, 'tco_triggered_in_expression', False):
                self.tco_triggered_in_expression = False
                self.current_assignment_lhs = old_lhs
                platform.abandon_scope()
                return
                
            num_targets = len(node.left.children)
            platform.end_scope(returns=num_targets)
            
            safe_regs = platform.get_safe_regs()
            for i in reversed(range(num_targets)):
                platform.pop(safe_regs[i])
                
            for i, target in enumerate(node.left.children):
                if target.node_type == NodeType.Identifier:
                    target_name = target.value
                    if target_name and target_name.startswith(".") and getattr(self, 'current_type_context', None):
                        target_name = self.current_type_context + target_name
                        
                    sym = self.get_symbol(target_name)
                    if sym:
                        platform.write_local(sym.fp_offset, safe_regs[i], node.value)
                    else:
                        platform.push(safe_regs[i])
                        self.declare_symbol(target_name)
                        platform.write_local(self.get_symbol(target_name).fp_offset, safe_regs[i], node.value)
                        
                elif target.node_type == NodeType.Lens and target.left is None:
                    for r in range(num_targets): 
                        platform.push(safe_regs[r])
                    
                    platform.start_scope()
                    self.current_assignment_lhs = None
                    self._compile_node(target.right)
                    self.current_assignment_lhs = node.left
                    platform.end_scope(returns=1)
                    
                    platform.pop(platform.t1)
                    for r in reversed(range(num_targets)): 
                        platform.pop(safe_regs[r])
                        
                    platform.store_deref(platform.t1, safe_regs[i])
    
        else:
            raise SyntaxError(f"Syntax logic check failed at {node.line}:{node.col}")

        self.current_assignment_lhs = old_lhs

    def MacroCall(self, node):
        self.enter_scope()
        platform.start_scope()
        start_fp_offset = getattr(self, 'local_fp_offset', 0)
        
        self.macro_expansion_counter += 1
        self.macro_expansion_stack.append(self.macro_expansion_counter)
        
        old_pure_out_var = self.pure_context_out_var
        self.pure_context_history.append(old_pure_out_var)
        
        if node.is_pure:
            self.pure_context_out_var = node.value 
        elif old_pure_out_var is not None:
            raise SyntaxError(f"VMG Integrity Map Failure at {node.line}:{node.col}")

        platform.push(platform.x0)
        out_sym = self.declare_symbol(node.value)
        
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = None
        
        old_branch_flag = getattr(self, 'macro_branch_emitted', False)
        self.macro_branch_emitted = False
        
        self._compile_node(node.left)
        
        self.macro_branch_emitted = old_branch_flag or self.macro_branch_emitted
        self.current_assignment_lhs = old_lhs
        self.pure_context_out_var = old_pure_out_var
        self.pure_context_history.pop()

        platform.read_local(platform.t0, out_sym.fp_offset, node.value)
        self.exit_scope()
        self.macro_expansion_stack.pop()

        platform.end_scope(returns=0)
        self.local_fp_offset = start_fp_offset
        platform.push(platform.t0)
    
    def _compile_statement_sequence(self, children):
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        
        for i, child in enumerate(children):
            if i < len(children) - 1:
                self.current_assignment_lhs = None
            else:
                self.current_assignment_lhs = old_lhs
                
            self._compile_node(child)
            
            if getattr(self, 'tco_triggered_in_expression', False):
                continue

        self.current_assignment_lhs = old_lhs

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
        platform.jump_and_link(platform.t0, skip_label)
        platform.emit_aligned_bytes(data)
        platform.label(skip_label)
        
        platform.push(platform.t0)
        platform.push_value(len(data))

    def _compile_asm(self, node):
        inst_name = node.children[0].value

        if self.pure_context_out_var is not None:
            if platform.is_mutating_instruction(inst_name):
                raise SyntaxError(f"Visible Mutation Guarantee Violation at {node.line}:{node.col}")

        args = list()
        has_rd = platform.has_rd_register(inst_name)
        
        temp_pool = platform.get_temp_regs_for_asm() 
        temp_idx = 0
        store_back_sym = None
        rd_reg_to_push = None
        output_name = None
        
        eval_args = []
        
        for i, arg in enumerate(node.children[1:]):
            if platform.is_branch_target(inst_name, i, len(node.children[1:])):
                self.macro_branch_emitted = True 
                val = arg.value if hasattr(arg, 'value') else arg
                if isinstance(val, str):
                    if getattr(self, 'macro_expansion_stack', None): 
                        val = f"{val}_mac{self.macro_expansion_stack[-1]}"
                    elif getattr(self, 'current_function_name', None): 
                        val = f"{val}_fn_{self.current_function_name.replace('.', '_')}"
                eval_args.append({'type': 'literal', 'val': val})
                continue

            if platform.is_immediate_arg(inst_name, i):
                val = arg.value if getattr(arg, 'node_type', None) == NodeType.Value else getattr(arg, 'value', arg)
                eval_args.append({'type': 'literal', 'val': val})
                continue

            name = getattr(arg, 'value', None)
            is_output = (i == 0 and has_rd)
            
            if isinstance(name, str) and platform.is_register(name):
                eval_args.append({'type': 'literal', 'val': platform.get_register(name)})
                if is_output: 
                    rd_reg_to_push = platform.get_register(name)
                continue
                
            if is_output:
                sym = self.get_symbol(name)
                if sym:
                    eval_args.append({'type': 'reg', 'val': 5})
                    rd_reg_to_push = 5
                    output_name = name
                    store_back_sym = sym
                else:
                    platform.push(platform.x0)
                    sym = self.declare_symbol(name)
                    eval_args.append({'type': 'reg', 'val': 5})
                    rd_reg_to_push = 5
                    output_name = name
                    store_back_sym = sym
            else:
                eval_args.append({'type': 'eval', 'node': arg})

        eval_nodes = [e for e in eval_args if e['type'] == 'eval']
        
        platform.start_scope()
        #TODO: bleed regs to stack.
        assert len(eval_nodes) <= len(temp_pool), f"Assembly expression requires {len(eval_nodes)} temporary registers, but only {len(temp_pool)} are available."

        for e in eval_nodes:
            self._compile_node(e['node'])
            
        for e in reversed(eval_nodes):
            tmp_reg = temp_pool[temp_idx]
            temp_idx += 1
            platform.pop(tmp_reg)
            e['reg'] = tmp_reg
            
        for e in eval_args:
            if e['type'] == 'eval': 
                args.append(e['reg'])
            elif e['type'] == 'reg': 
                args.append(e['val'])
            else: 
                args.append(e['val'])
        try:        
            platform.emit_instruction(inst_name, *args)
        except AttributeError :
            raise AttributeError(f"attrib error raised from node: {inst_name}, {self.current_type_context} {node.line}:{node.col}")
        if store_back_sym:
            platform.write_local(store_back_sym.fp_offset, rd_reg_to_push, output_name)
            platform.end_scope(returns=0)
        else:
            if rd_reg_to_push is not None:
                platform.push(rd_reg_to_push)
                platform.end_scope(returns=1)
            else:
                platform.end_scope(returns=0)

    def Tuple(self, node):
        for child in node.children: 
            self._compile_node(child)

    def Value(self, node):
        if isinstance(node.value, str):
            raise SyntaxError(f"Cannot allocate static .rodata inside a dynamic stack scope at {node.line}:{node.col}. Bind strings as namespace statics instead.")
        platform.push_value(node.value)