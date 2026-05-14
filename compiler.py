import platform
import tokens
import AST
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
        assert isinstance(main_filepath, str) and main_filepath, "Project entry point must be a valid, non-empty file path string"
        assert main_filepath.endswith('.w') or '.' in main_filepath, "File extension expected for main source file"
        
        self.discover_file(main_filepath)
        full_ast = self.semantic_parse_file(main_filepath)
        
        assert full_ast.node_type == NodeType.Program, "Compilation structural entry point must be a Program node"
        
        comp = Compiler()
        result_platform = comp.compile(full_ast)
        
        assert result_platform is not None, "Compiler failed to yield a valid assembly block representation"
        assert hasattr(result_platform, 'get_code_length') and result_platform.get_code_length() > 0, "Compilation critically output zero executable machine code instructions targeting bare minimum evaluation"
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
            
        if node.node_type == NodeType.FunctionDef:
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
        
        assert ast_full.node_type == NodeType.Program, "Semantic parse routine must definitively yield a Program root node"
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
    offset_from_base: int  

class Compiler:
    def __init__(self, cpu_lib=None, cpu_state_type=None):
        self.scopes: List[Dict[str, SymbolInfo]] = [{}]
        self.current_stack_depth = 0
        self.label_counter = 0
        self.function_registry = {}
        self.pure_context_out_var = None
        self.pure_context_history =[]
        self.comptime_evaluator = None 
        self.macro_expansion_counter = 0
        self.macro_expansion_stack = []

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
        assert label.startswith(prefix), "Generated label critically failed to inherit the requested system prefix"
        return label

    def compile(self, node: ASTNode):
        assert node is not None and hasattr(node, 'node_type'), "Compiler evaluation requires a populated, valid root AST Node"
        assert node.node_type == NodeType.Program, "Compilation matrix must strictly initialize at a Program root node"
        
        platform.init()
        self._register_functions(node)
        self._compile_node(node)
        
        assert len(self.scopes) == 1, f"Compiler execution leaked {len(self.scopes) - 1} un-exited scope layers upon finish"
        assert self.current_stack_depth == 0, f"Compilation fully leaked structural hardware memory frame bounds maintaining unresolved {self.current_stack_depth} byte total footprint sequence"
        return platform
    
    def validate_and_get_offset(self, target_offset_from_base, name: str, negative = False) -> int:
        offset = target_offset_from_base - self.current_stack_depth
        
        # New Strict Validation logic to catch the drift
        if negative:
            assert offset <= -platform.REGISTER_SIZE, f"Memory read error: Calculated offset {offset} for '{name}' targets the unallocated stack tip or above."
        else:
            assert offset < 0, f"Memory offset constraint failed: Calculated relative offset {offset} pushes purely into positive disjoint bounds for '{name}'."
            
        assert offset % platform.REGISTER_SIZE == 0, f"Hardware offset memory fetch definitively broke structural alignment bounds: {offset}"

        return offset

    def _register_functions(self, node: ASTNode, current_type_context=None):
        if not node: 
            return
        
        if node.node_type == NodeType.FunctionDef:
            assert isinstance(node.value, str) and node.value, "Function definition inherently requires an explicit structural name"
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
                assert len(node.children) > 0, "Function architectural mapping requires at least 1 executable block sequence child"
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
        assert isinstance(func_name, str) and func_name, "Mangling requires a valid string-based root name"
        assert isinstance(pat_args, list), "Pattern arguments must be passed strictly as an iterable parameter list"
        
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
        assert hasattr(node, 'node_type'), "Target instruction block is not a mapped ASTNode variant"
        
        method_name = node.node_type.name
        visitor = getattr(self, method_name, self.error)
        
        return visitor(node)
      
    def _ast_nodes_equal(self, n1, n2):
        if n1 is None and n2 is None: return True
        if n1 is None or n2 is None: return False
        assert hasattr(n1, 'node_type') and hasattr(n2, 'node_type'), "Structural map comparisons must strictly exclusively analyze identical AST framework nodes"
        
        if n1.node_type != n2.node_type: return False
        if n1.value != n2.value: return False
        if len(n1.children) != len(n2.children): return False
        for c1, c2 in zip(n1.children, n2.children):
            if not self._ast_nodes_equal(c1, c2): return False
        if not self._ast_nodes_equal(n1.left, n2.left): return False
        if not self._ast_nodes_equal(n1.right, n2.right): return False
        return True
    
    def error(self, node):
        raise NotImplementedError(f"CRITICAL: Unmapped evaluation method for AST structure {node.node_type} at line {node.line}:{node.col}")
    
    def get_symbol(self, name: str) -> Optional[SymbolInfo]:
        assert isinstance(name, str) and name, "Symbol map lookup key strictly requests a valid string type"
        assert len(self.scopes) > 0, "Global invariant fault: Attempting to lookup symbol with zero active scope frames"
        
        for scope in reversed(self.scopes):
            if name in scope:
                sym = scope[name]
                assert isinstance(sym, SymbolInfo), "Symbol mapping critically failed to yield a typed SymbolInfo object"
                assert sym.offset_from_base % platform.REGISTER_SIZE == 0, f"Symbol '{name}' offset must be strictly register-aligned"
                assert sym.offset_from_base <= self.current_stack_depth, f"Symbol '{name}' offset {sym.offset_from_base} logically violates current stack depth limit mapping {self.current_stack_depth}"
                return sym
                
        return None

    def declare_symbol(self, name: str):
        assert isinstance(name, str) and name, "Symbol layout declaration requires an exact string name"
        assert len(self.scopes) > 0, "Local layer assignment invariant violated: No active scope exists"
        assert name not in self.scopes[-1], f"Local variable '{name}' overlaps an already defined footprint in the active scope layer"
        assert self.current_stack_depth >= platform.REGISTER_SIZE, "Hardware layout calculation prohibits declaring symbols with no stack space allocated"
        
        info = SymbolInfo(offset_from_base=self.current_stack_depth - platform.REGISTER_SIZE)
        
        assert info.offset_from_base >= 0, f"Symbol offset {info.offset_from_base} mathematically violates minimum positive stack space."
        assert info.offset_from_base <= self.current_stack_depth - platform.REGISTER_SIZE, f"Symbol declaration error: Recorded absolute offset {info.offset_from_base} identically points to the current empty SP tip, not the physically populated slot beneath it."
        assert info.offset_from_base % platform.REGISTER_SIZE == 0, f"Hardware violation: Local variable offset {info.offset_from_base} misaligned to the {platform.REGISTER_SIZE} byte boundaries"
        
        self.scopes[-1][name] = info
        assert self.scopes[-1][name] is info, "Symbol mapping strictly failed to bind new layout info to active scope map structure"
        return info


    def Identifier(self, node):
        assert node.node_type == NodeType.Identifier, "Node routed to Identifier phase strictly requires matching internal typing"
        assert isinstance(node.value, str) and node.value, "Raw identifier entity maps to an uninitialized runtime value"
        assert self.current_stack_depth >= 0, "Stack pointer baseline corrupted prior to identifier evaluation"
        
        name = node.value
        if name.startswith(".") and getattr(self, 'current_type_context', None):
            name = self.current_type_context + name

        if hasattr(self, 'static_fields') and name in self.static_fields:
            val = self.static_fields[name]
            if isinstance(val, str):
                data = val.encode('utf-8')
                skip_label = self.get_unique_label("skip_str")
                platform.jump_and_link(platform.t0, skip_label)
                platform.emit_bytes(data)
                
                padding = (platform.REGISTER_SIZE - (len(data) % platform.REGISTER_SIZE)) % platform.REGISTER_SIZE
                if padding > 0:
                    platform.emit_bytes(b'\x00' * padding)
                    
                platform.label(skip_label)
                
                platform.push(platform.t0)
                self.current_stack_depth += platform.REGISTER_SIZE
                platform.push_value(len(data))
                self.current_stack_depth += platform.REGISTER_SIZE
            else:
                platform.push_value(val)
                self.current_stack_depth += platform.REGISTER_SIZE
            return

        sym = self.get_symbol(node.value)
        if not sym: 
            if node.type_name:
                platform.push(platform.x0)
                self.current_stack_depth += platform.REGISTER_SIZE
                sym = self.declare_symbol(node.value)
                return
            raise ValueError(f"Undefined variable footprint lookup: '{node.value}' at line {node.line}:{node.col}")
            
        offset = sym.offset_from_base - self.current_stack_depth
        
        # Explicit sanity check ensuring variable wasn't structurally discarded before retrieval
        assert sym.offset_from_base <= self.current_stack_depth - platform.REGISTER_SIZE, f"Variable '{node.value}' destruction detected: Recorded base offset {sym.offset_from_base} resides above the current tracking stack pointer bounds."
        
        self.validate_and_get_offset(sym.offset_from_base, node.value, negative=True)
        assert abs(offset) < (15 * platform.REGISTER_SIZE), f"Memory offset {offset} for '{node.value}' exceeds all logical bounds of the caller frame map footprint."
        
        platform.read_local(platform.t0, offset) 
        platform.push(platform.t0)
        self.current_stack_depth += platform.REGISTER_SIZE
        
        assert self.current_stack_depth >= platform.REGISTER_SIZE, "Stack depth evaluation physically unbalanced tracking after valid Identifier pull"

    def FunctionDef(self, node):
    
        assert node.node_type == NodeType.FunctionDef, "Instruction branch map mistargeted FunctionDef variant"
        assert isinstance(node.value, str) and node.value, "Compiler strict mapping inherently requires function name assignments"
        assert len(node.children) > 0, "Execution block definition contains no structurally executable nodes"
        
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
        
        self.enter_scope()
        old_stack_depth = self.current_stack_depth
        self.current_stack_depth = 0
        
        platform.push(platform.ra)
        self.current_stack_depth += platform.REGISTER_SIZE
        
        assert self.current_stack_depth == platform.REGISTER_SIZE, "Stack physics mapping crucially requires exact RA baseline registration initialization depth"
        
        offset = 0
        for p in reversed(pat_args):
            offset -= platform.REGISTER_SIZE
            assert p.node_type in (NodeType.Identifier, NodeType.Value, NodeType.Tuple, NodeType.Lens), f"Evaluation expects standard AST signature pattern parameter, got {p.node_type}"
            
            p_name = None
            if p.node_type == NodeType.Identifier:
                p_name = p.value
            elif p.node_type == NodeType.Lens:
                assert p.left is not None and p.left.node_type == NodeType.Identifier, "Lens parameter base must be an identifier"
                p_name = p.left.value
                
            if p_name is not None:
                info = SymbolInfo(offset_from_base=offset)
                self.validate_and_get_offset(offset, node.value, negative=True)
                self.scopes[-1][p_name] = info
            
        assert offset == -len(pat_args) * platform.REGISTER_SIZE, "Frame mapping mathematics critically bypassed evaluating standard parameter footprint structures"
        
        platform.push(platform.x0)
        self.current_stack_depth += platform.REGISTER_SIZE
        
        for rv in ret_nodes:
            if rv.node_type == NodeType.Identifier:
                if rv.value not in self.scopes[-1]:
                    platform.push(platform.x0)
                    self.current_stack_depth += platform.REGISTER_SIZE
                    self.declare_symbol(rv.value)

        platform.label(func_label + "_loop")
            
        old_type_ctx = getattr(self, 'current_type_context', None)
        self.current_type_context = func_name
        
        old_loop_base = getattr(self, 'loop_base_depth', None)
        self.loop_base_depth = self.current_stack_depth
        
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = None
        
        expected_body_depth = self.current_stack_depth
        assert expected_body_depth >= 2 * platform.REGISTER_SIZE, "Callee scope bounds fatally failed establishing bare minimum layout (RA + 0-init) requirements"
        
        self._compile_node(body)
        
        assert self.current_stack_depth == expected_body_depth, f"Memory leak dynamically established! Expected block stack depth {expected_body_depth}, ended with {self.current_stack_depth}"
        
        self.current_assignment_lhs = old_lhs
        self.loop_base_depth = old_loop_base
        self.current_type_context = old_type_ctx
        self.current_return_node = old_ret_node
        
        safe_regs = platform.get_safe_regs()
        assert len(ret_nodes) <= len(safe_regs), "Method signature declares return parameters explicitly exceeding the safe internal RISC transport bridge"
        
        if ret_nodes:
            for rv in ret_nodes:
                self._compile_node(rv)
            for i in reversed(range(len(ret_nodes))):
                platform.pop(safe_regs[i])
                self.current_stack_depth -= platform.REGISTER_SIZE
        else:
            platform.load_immediate(safe_regs[0], 0)
        
        diff = self.current_stack_depth - platform.REGISTER_SIZE
        assert diff >= 0, f"Calley frame shrink constraint crashed: Depth {self.current_stack_depth} physically undercut the fundamental return address mark!"
        
        if diff > 0:
            platform.shrink_stack(diff)
            self.current_stack_depth = platform.REGISTER_SIZE
            
        platform.pop(platform.ra)
        self.current_stack_depth -= platform.REGISTER_SIZE
        
        assert self.current_stack_depth == 0, "Execution callee bounds assert failed: Depth must hit strict flat zero mark prior to pipeline jalr branch logic"
        
        platform.return_jump()
        
        self.current_stack_depth = old_stack_depth
        self.exit_scope()
        self.current_function_name = old_func_name
        
        platform.label(skip_label)
        assert self.current_stack_depth == old_stack_depth, "Parent scope map fatally injured compiling dynamic child layout definition footprint"
    
    def Call(self, node):
        assert node.node_type == NodeType.Call, "Node operation request branch incorrectly evaluates logic map"
        assert isinstance(node.value, str) and node.value, "Invocation mechanism maps entirely blank execution bounds"
        assert isinstance(node.children, list), "Transmission pattern mandates structural array wrapping for parameter sequences"
        
        func_name = node.value
        call_args = node.children
        
        if func_name.startswith(".") and getattr(self, 'current_type_context', None):
            func_name = self.current_type_context + func_name
            
        defs = self.function_registry.get(func_name, [])
        defs = [d for d in defs if len(d['pat_args']) == len(call_args)]
        
        if not defs:
            raise ValueError(f"No matching overloaded signature configuration found for branch '{func_name}' mapping {len(call_args)} distinct args at line {node.line}:{node.col}")

        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = None
        
        initial_depth = self.current_stack_depth
        
        for arg in call_args:
            depth_before_arg = self.current_stack_depth
            self._compile_node(arg)
            assert self.current_stack_depth == depth_before_arg + platform.REGISTER_SIZE, f"Expression '{getattr(arg, 'value', arg.node_type)}' yielded abnormal bit size layout skewing runtime memory map alignment"
            
        self.current_assignment_lhs = old_lhs
        
        expected_arg_bytes = len(call_args) * platform.REGISTER_SIZE
        assert self.current_stack_depth == initial_depth + expected_arg_bytes, f"Arg frame computation mismatch: pushed {self.current_stack_depth - initial_depth} bytes, mathematically expected {expected_arg_bytes}"
            
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
                    if getattr(call_args[i], 'node_type', None) == NodeType.Value:
                        if call_args[i].value != p.value:
                            static_fail = True
                            break
                        else:
                            continue
                            
                    has_runtime_checks = True
                    offset_from_top = (len(call_args) - i) * platform.REGISTER_SIZE
                    
                    assert offset_from_top >= platform.REGISTER_SIZE, f"Dispatch layout error: Offset {-offset_from_top} targets the unallocated SP tip (0). Pushed arguments mathematically reside in negative space."
                    assert offset_from_top > 0 and offset_from_top <= expected_arg_bytes, f"Dispatch read check maps completely disjoint index bounds {offset_from_top}"
                    assert offset_from_top % platform.REGISTER_SIZE == 0, "Dynamic dispatch index verification misaligned strict structural constraints"
                    
                    platform.read_local(platform.t0, -offset_from_top)
                    platform.load_immediate(platform.t1, p.value)
                    platform.branch_not_equal(platform.t0, platform.t1, next_def_label)
                    
            if static_fail:
                continue
                
            if is_tro:
                saved_depth = self.current_stack_depth
                temp_regs = platform.get_temp_regs_for_tco(len(pat_args))
                assert len(temp_regs) == len(pat_args), "Insufficient strict hardware execution registers to hold active TCO unwinding payloads"
                
                for reg in reversed(temp_regs):
                    platform.pop(reg)
                    self.current_stack_depth -= platform.REGISTER_SIZE
                
                assert self.current_stack_depth == saved_depth - expected_arg_bytes, f"Stack unwind alignment mathematically missed layout requirement bounds post-TCO argument pop. Expected {saved_depth - expected_arg_bytes}, got {self.current_stack_depth}."
                
                num_args = len(temp_regs)
                for i, reg in enumerate(temp_regs):
                    # Mathematical inversion linking target parameter array placement directly to frame bounds
                    target_offset_from_base = -platform.REGISTER_SIZE * (num_args - i)
                    
                    offset = target_offset_from_base - self.current_stack_depth
                    self.validate_and_get_offset(target_offset_from_base, node.value)
                    
                    platform.write_local(offset, reg)
                    
                diff = self.current_stack_depth - getattr(self, 'loop_base_depth', platform.REGISTER_SIZE)
                assert diff >= 0, f"TCO parameter evaluation base overlap failed runtime logic geometry constraint! Diff calculation returned negative: {diff}"
                assert diff % platform.REGISTER_SIZE == 0, f"Tail recursion shrink constraint misaligned completely against register sizes: {diff}"
                
                if diff > 0:
                    platform.shrink_stack(diff)
                    
                platform.jump(definition['label'] + "_loop")
                self.current_stack_depth = saved_depth
            else:
                platform.call(definition['label'])
                platform.jump(end_dispatch_label)
                
            platform.label(next_def_label)
            
            if not has_runtime_checks:
                match_found_statically = True
                break
                
        if not match_found_statically:
            platform.halt()
            
        platform.label(end_dispatch_label)
        
        num_returns = len(defs[0]['ret_nodes']) if defs else 1
        safe_regs = platform.get_safe_regs()

        if is_tro:
            self.current_stack_depth -= expected_arg_bytes
            for _ in range(num_returns if num_returns > 0 else 1):
                platform.push(platform.x0) 
                self.current_stack_depth += platform.REGISTER_SIZE
                
            assert self.current_stack_depth == initial_depth + ((num_returns if num_returns > 0 else 1) * platform.REGISTER_SIZE), "TCO state logic exited map strictly missing correct payload delivery structure dimensions"
        else:
            num_args = len(call_args)
            if num_args > 0:
                platform.shrink_stack(num_args * platform.REGISTER_SIZE)
                self.current_stack_depth -= (num_args * platform.REGISTER_SIZE)
            
            assert self.current_stack_depth == initial_depth, f"Call framework strictly mandates stack pointer reversion fully prior to output integration execution. Failed bounds {self.current_stack_depth} != {initial_depth}"
            
            if num_returns > 0:
                for i in range(num_returns):
                    platform.push(safe_regs[i])
                    self.current_stack_depth += platform.REGISTER_SIZE
            else:
                platform.push(safe_regs[0])
                self.current_stack_depth += platform.REGISTER_SIZE
                
        assert self.current_stack_depth == initial_depth + (max(num_returns, 1) * platform.REGISTER_SIZE), "Execution framework entirely missed safe register pushing logic requirements post-call evaluation block"

    def Lens(self, node):
        assert getattr(node, 'node_type', None) == NodeType.Lens, "Routing explicitly requires Lens mapped node structures"
        
        initial_depth = self.current_stack_depth
        
        if node.left is None:
            # Prefix Lens logic (Pointer Deref) -> [ptr]
            self._compile_node(node.right)
            
            assert self.current_stack_depth == initial_depth + platform.REGISTER_SIZE, "Execution pointer logic mathematically failed pushing exactly one completely verified address bounds physically establishing memory boundary sequence footprint purely"
            
            platform.pop(platform.t0) 
            self.current_stack_depth -= platform.REGISTER_SIZE
            
            platform.load_deref(platform.t1, platform.t0)
            platform.push(platform.t1)
            self.current_stack_depth += platform.REGISTER_SIZE
            
            assert self.current_stack_depth == initial_depth + platform.REGISTER_SIZE, "Target memory layout sequence completely damaged execution stack array limits physically rendering exactly valid mapped offset parameters strictly establishing correct frame physics completely unconditionally mapping bounds executing completely unconditionally"
        else:
            # Infix Lens logic (Slice / Data Pluck) -> arr[0:4]
            # 1. Evaluate the base footprint (e.g., .str physically pushes 2 registers)
            self._compile_node(node.left)
            pushed_base_bytes = self.current_stack_depth - initial_depth
            assert pushed_base_bytes >= platform.REGISTER_SIZE, "Lens base evaluation fundamentally failed establishing physical hardware layout"

            total_elements = pushed_base_bytes // platform.REGISTER_SIZE
            inner = node.right
            
            # 2. Resolve bounds natively
            if inner.node_type == NodeType.Value:
                # [0] -> [0:0] behavior natively applied
                start_idx = inner.value
                end_idx = inner.value
            elif inner.node_type == NodeType.Pipeline:
                # [0:1] bounds
                assert inner.left.node_type == NodeType.Value, "Lens start must be a compile-time static integer for DOD tuples"
                assert inner.right.node_type == NodeType.Value, "Lens end must be a compile-time static integer for DOD tuples"
                start_idx = inner.left.value
                end_idx = inner.right.value
            else:
                raise NotImplementedError("Dynamic slice bounds requiring runtime logic not yet implemented")

            if end_idx == -1:
                end_idx = total_elements - 1

            assert 0 <= start_idx <= end_idx < total_elements, f"Lens bounds [{start_idx}:{end_idx}] physically breach stack sequence size {total_elements} for '{getattr(node.left, 'value', 'expr')}'"

            elements_to_keep = (end_idx - start_idx) + 1
            
            # 3. Pluck the requested registers from the pushed sequence
            temp_regs = platform.get_temp_regs_for_tco(elements_to_keep)
            for i in range(elements_to_keep):
                # Index 0 is mathematically the "bottom" register (the one pushed first)
                offset_from_top = pushed_base_bytes - ((start_idx + i) * platform.REGISTER_SIZE)
                platform.read_local(temp_regs[i], -offset_from_top)
                
            # 4. Obliterate the old flat sequence entirely to prevent leaks
            platform.shrink_stack(pushed_base_bytes)
            self.current_stack_depth -= pushed_base_bytes
            
            # 5. Push ONLY the exact requested isolated slices back onto the active stack tip
            for i in range(elements_to_keep):
                platform.push(temp_regs[i])
                self.current_stack_depth += platform.REGISTER_SIZE

            assert self.current_stack_depth == initial_depth + (elements_to_keep * platform.REGISTER_SIZE), "Lens sequence physically failed strict layout reversion boundaries"



    def Assignment(self, node):
        assert node.node_type == NodeType.Assignment, "Operator node routing misaligned completely bypassing strict framework typing"
        assert node.left is not None and node.right is not None, "Algebraic bounds stricture requires execution mapping fully on both adjacent sequence sides"
        assert self.pure_context_out_var is None or isinstance(self.pure_context_out_var, str), "Invalid memory mutation mapping tracked silently in pure scope boundaries"
        
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = node.left

        if self.pure_context_out_var is not None:
            if node.left.node_type == NodeType.Identifier:
                assert node.left.value == self.pure_context_out_var, f"Visible Mutation Guarantee Violation at {node.line}:{node.col} -> Pure macro absolutely cannot arbitrarily mutate external binding '{node.left.value}'"
            elif node.left.node_type == NodeType.Lens and node.left.left is None:
                raise SyntaxError(f"Visible Mutation Guarantee Violation at {node.line}:{node.col} -> Pure macro contexts are definitively barred from corrupting unknown memory space via blind Lens assignment logic")

        initial_depth = self.current_stack_depth

        if node.left.node_type == NodeType.Identifier:
            name = node.left.value
            
            if name and name.startswith(".") and getattr(self, 'current_type_context', None):
                name = self.current_type_context + name
                node.left.value = name
                
                if not hasattr(self, 'static_fields'):
                    self.static_fields = {}
                    
                rhs_node = node.right
                if getattr(rhs_node, 'node_type', None) == NodeType.Call and rhs_node.value == self.current_type_context:
                    assert len(rhs_node.children) == 1, f"Self-referential static constructor '{self.current_type_context}' strictly mandates exactly one initialization literal parameter"
                    rhs_node = rhs_node.children[0]
                    
                if getattr(rhs_node, 'node_type', None) == NodeType.Value:
                    self.static_fields[name] = rhs_node.value
                    self.current_assignment_lhs = old_lhs
                    assert self.current_stack_depth == initial_depth, "Static construction entirely skewed mapping executing assignment bounds mapping logic exactly"
                    return
                
            self._compile_node(node.right)
            
            assert self.current_stack_depth == initial_depth + platform.REGISTER_SIZE, "RHS evaluation logic fundamentally maps standard assignments solely issuing 1 data segment exactly per operation"
            
            sym = self.get_symbol(name)
            if sym:
                assert sym.offset_from_base <= self.current_stack_depth - platform.REGISTER_SIZE, f"Attempting to overwrite destroyed or invalid variable '{name}' offset location {sym.offset_from_base}"
                
                platform.pop(platform.t0)
                self.current_stack_depth -= platform.REGISTER_SIZE
                
                offset = sym.offset_from_base - self.current_stack_depth
                self.validate_and_get_offset(sym.offset_from_base, node.value, negative=True)
                assert offset < 0, f"Assignment overwrite memory offset constraint failure: {offset} is not natively pointing backwards down the footprint tree!"
                platform.write_local(offset, platform.t0)
            else:
                self.declare_symbol(name)

        elif node.left.node_type == NodeType.Lens and node.left.left is None:
            self.current_assignment_lhs = None
            self._compile_node(node.left.right)
            
            assert self.current_stack_depth == initial_depth + platform.REGISTER_SIZE, "Target memory layout array access definitively failed producing valid strictly singular base address"
            
            self.current_assignment_lhs = node.left
            self._compile_node(node.right)
            
            assert self.current_stack_depth == initial_depth + 2 * platform.REGISTER_SIZE, "Lens memory calculation misaligned stack requirement executing base load and RHS payload bounds"
            
            platform.pop(platform.t0)
            self.current_stack_depth -= platform.REGISTER_SIZE
            platform.pop(platform.t1)
            self.current_stack_depth -= platform.REGISTER_SIZE
            
            platform.store_deref(platform.t1, platform.t0)
            
        elif node.left.node_type == NodeType.Tuple:
            self._compile_node(node.right)
            
            num_targets = len(node.left.children)
            assert self.current_stack_depth - initial_depth == num_targets * platform.REGISTER_SIZE, f"Tuple split mechanism completely overshot stack frame bounds delivering {(self.current_stack_depth - initial_depth) // platform.REGISTER_SIZE} components instead of mandatory {num_targets}"
            
            safe_regs = platform.get_safe_regs()
            assert num_targets <= len(safe_regs), "Total layout constraint completely outnumbers strictly assigned sequence transit pathways"
            
            for i in reversed(range(num_targets)):
                platform.pop(safe_regs[i])
                self.current_stack_depth -= platform.REGISTER_SIZE
                
            for i, target in enumerate(node.left.children):
                if target.node_type == NodeType.Identifier:
                    target_name = target.value
                    if target_name and target_name.startswith(".") and getattr(self, 'current_type_context', None):
                        target_name = self.current_type_context + target_name
                        
                    sym = self.get_symbol(target_name)
                    if sym:
                        assert sym.offset_from_base <= self.current_stack_depth, f"Tuple assignment targeting destroyed scope binding {target_name}"
                        offset = sym.offset_from_base - self.current_stack_depth
                        self.validate_and_get_offset(sym.offset_from_base, node.value, negative=True)
                        platform.write_local(offset, safe_regs[i])
                    else:
                        platform.push(safe_regs[i])
                        self.current_stack_depth += platform.REGISTER_SIZE
                        self.declare_symbol(target_name)
                        
                elif target.node_type == NodeType.Lens and target.left is None:
                    for r in range(num_targets):
                        platform.push(safe_regs[r])
                        self.current_stack_depth += platform.REGISTER_SIZE
                    
                    depth_before_ptr = self.current_stack_depth
                    self.current_assignment_lhs = None
                    self._compile_node(target.right)
                    
                    assert self.current_stack_depth == depth_before_ptr + platform.REGISTER_SIZE, "Evaluation of unpack pointer explicitly corrupted executing scope tracking parameters"
                    self.current_assignment_lhs = node.left
                    
                    platform.pop(platform.t1)
                    self.current_stack_depth -= platform.REGISTER_SIZE
                    
                    for r in reversed(range(num_targets)):
                        platform.pop(safe_regs[r])
                        self.current_stack_depth -= platform.REGISTER_SIZE
                    
                    platform.store_deref(platform.t1, safe_regs[i])
        else:
            raise SyntaxError(f"Syntax logic check failed unconditionally at line {node.line}:{node.col} -> Mapping execution target mapped unsupported assignment AST bounds {node.left.node_type.name}")
            
        self.current_assignment_lhs = old_lhs
        assert self.current_stack_depth >= initial_depth, f"Assignment hardware logic sequence executed impossible stack loss shrinking original boundary baseline frame parameters. End depth: {self.current_stack_depth}"

    def MacroCall(self, node):
        assert node.node_type == NodeType.MacroCall, "Runtime bounds sequence bypassed correctly mapped instruction tree"
        assert isinstance(node.value, str) and node.value, "Macro implementation mandates strict assignment naming sequence parameters"
        
        self.enter_scope()
        start_depth = self.current_stack_depth
        
        self.macro_expansion_counter += 1
        self.macro_expansion_stack.append(self.macro_expansion_counter)
        
        old_pure_out_var = self.pure_context_out_var
        self.pure_context_history.append(old_pure_out_var)
        
        if node.is_pure:
            self.pure_context_out_var = node.value 
            assert not (old_pure_out_var is not None and node.value != old_pure_out_var), "Pure context nesting structurally prohibits mutation tracking overriding distinct execution target mappings"
        elif old_pure_out_var is not None:
            raise SyntaxError(f"VMG Integrity Map Failure at {node.line}:{node.col}")

        platform.push(platform.x0)
        self.current_stack_depth += platform.REGISTER_SIZE
        out_sym = self.declare_symbol(node.value)
        
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        self.current_assignment_lhs = None
        
        old_branch_flag = getattr(self, 'macro_branch_emitted', False)
        self.macro_branch_emitted = False
        
        self._compile_node(node.left)
        
        body_diff = self.current_stack_depth - (start_depth + platform.REGISTER_SIZE)
        if self.macro_branch_emitted:
            assert body_diff == 0, f"Control flow alignment error: Macro '{node.value}' contains internal branches but resulted in a net stack change of {body_diff} bytes. Conditional execution of stack-modifying instructions (like raw hardware output pushes or new variable declarations) will fatally desynchronize the runtime stack pointer if the block branches, causing severe memory corruption and infinite loops."
            
        self.macro_branch_emitted = old_branch_flag or self.macro_branch_emitted
        
        assert self.current_stack_depth >= start_depth + platform.REGISTER_SIZE, "Inline macro tree instruction completely discarded executing local parameter initialization scope boundary"
        
        self.current_assignment_lhs = old_lhs
        
        self.pure_context_out_var = old_pure_out_var
        self.pure_context_history.pop()

        offset = out_sym.offset_from_base - self.current_stack_depth
        
        self.validate_and_get_offset(out_sym.offset_from_base, node.value, negative=True)
        platform.read_local(platform.t0, offset)
        self.exit_scope()
        self.macro_expansion_stack.pop()

        diff = self.current_stack_depth - start_depth
        assert diff >= 0, "Macro map execution entirely shattered execution hardware bounds rendering negative stack memory frames impossible"
        
        if diff > 0:
            platform.shrink_stack(diff)
            self.current_stack_depth = start_depth

        platform.push(platform.t0)
        self.current_stack_depth = start_depth + platform.REGISTER_SIZE
        
        assert self.current_stack_depth == start_depth + platform.REGISTER_SIZE, "Macro block mapping logic critically bypassed safe execution returning completely misaligned physical bounds"
    
    
    def CallerContext(self, node):
        assert node is not None and node.node_type == NodeType.CallerContext, "Execution boundaries mandate strict type parameter mappings exclusively utilizing target node classes"
        assert hasattr(node, 'left'), "Caller logic context strictly demands valid singular left sequence mapping argument"
        assert self.pure_context_out_var is None or isinstance(self.pure_context_out_var, str), "State mutation logic strictly misaligned prior executing context mapped layer logic"

        saved_pure = self.pure_context_out_var
        popped = False
        saved_history_val = None
        
        if self.pure_context_history:
            saved_history_val = self.pure_context_history.pop()
            self.pure_context_out_var = saved_history_val
            popped = True
            
        self._compile_node(node.left)
        
        if popped:
            self.pure_context_history.append(saved_history_val)
            
        self.pure_context_out_var = saved_pure
      
    def _compile_statement_sequence(self, children):
        
        start_depth = self.current_stack_depth
        old_lhs = getattr(self, 'current_assignment_lhs', None)
        
        for i, child in enumerate(children):
            if i < len(children) - 1:
                self.current_assignment_lhs = None
            else:
                self.current_assignment_lhs = old_lhs
                
            depth_before = self.current_stack_depth
            scope_size_before = len(self.scopes[-1])
            
            self._compile_node(child)
            
            # Identify unbound bytes leaked by expression statements
            diff = self.current_stack_depth - depth_before
            expected_growth = (len(self.scopes[-1]) - scope_size_before) * platform.REGISTER_SIZE
            unbound_bytes = diff - expected_growth
            
            assert unbound_bytes >= 0, "Statement evaluation fundamentally corrupted stack layout, returning a negative differential."
            assert unbound_bytes % platform.REGISTER_SIZE == 0, "Unbound leaked bytes misaligned to strict register parameters."
            
            if unbound_bytes > 0:
                # Dynamically drop unbound expression leaks from the executing stack runtime
                platform.shrink_stack(unbound_bytes)
                self.current_stack_depth -= unbound_bytes
                
        self.current_assignment_lhs = old_lhs
        
        diff = self.current_stack_depth - start_depth
        assert diff >= 0, f"Block scope mapping physically damaged local runtime hardware bounds returning negative differential sequence map bytes {diff}"
        
        if diff > 0:
            platform.shrink_stack(diff)
            self.current_stack_depth = start_depth

    def Block(self, node):
        assert node.node_type == NodeType.Block, "Block instruction routing mismatched strictly required internal AST identification parameters"
        
        start_depth = self.current_stack_depth
        self.enter_scope()
        self._compile_statement_sequence(node.children)
    
        self.exit_scope()
        
        assert self.current_stack_depth == start_depth, "Block bounds fundamentally executed breaking stack layout requirements targeting exact baseline parameters fully mapping layouts"

    def Program(self, node):
        assert node.node_type == NodeType.Program, "Program execution strict parameter mapping demands immediate top level boundary configuration nodes entirely mapping entry execution blocks"
        
        # Implicit top-level namespace initialization
        old_ctx = getattr(self, 'current_type_context', None)
        self.current_type_context = "main"
        
        self._compile_statement_sequence(node.children)
            
        self.current_type_context = old_ctx
        platform.halt()
    
    def MacroDef(self, node):
        assert node.node_type == NodeType.MacroDef, "Macro execution parameter block structure boundaries physically overwritten bypassing logic maps"

    def Pipeline(self, node):
        assert node.node_type == NodeType.Pipeline, "Sequence logic execution requires completely standard AST architecture targets strictly following pipeline mappings"
        assert node.left is not None, "Pipeline runtime mappings demand immediate populated left sequences unconditionally mapping execution flow logic bounds"
        
        self._compile_node(node.left)
        if node.right:
            self._compile_node(node.right)

    def Intrinsic(self, node):
        assert node.node_type == NodeType.Intrinsic, "System bounds mapping mandates intrinsically configured node mappings exactly matching hardware requirements"
        assert node.value in["asm", "embed", "import", "using"], f"Intrinsic map limits entirely missed defining execution parameter branches logically supporting target constraint limits {node.value}"
        
        if node.value == "asm":
            self._compile_asm(node)
        elif node.value == "embed":
            self._compile_embed(node)

    def _compile_embed(self, node):
        assert len(node.children) == 1, "Embed path architecture map bounds structurally prohibit handling multiple target branch constraints simultaneously defining mappings exactly once"
        
        path = node.children[0].value
        assert isinstance(path, str) and path, "Hardware loading parameter map target strictly bounds strings defining target location pathways entirely matching file strings"
        
        with open(path, "rb") as f:
            data = f.read()
            
        assert data is not None, "Hardware binary boundary bounds mapped directly loading blank execution sequences unconditionally missing parameter bounds logic configurations entirely mapping null bytes sequences"
        
        skip_label = self.get_unique_label("skip_embed")
        platform.jump_and_link(platform.t0, skip_label)
        platform.emit_bytes(data)
        
        padding = (platform.REGISTER_SIZE - (len(data) % platform.REGISTER_SIZE)) % platform.REGISTER_SIZE
        if padding > 0:
            platform.emit_bytes(b'\x00' * padding)
            
        platform.label(skip_label)
        
        # 1. Push the memory address pointer
        platform.push(platform.t0)
        self.current_stack_depth += platform.REGISTER_SIZE
        
        # 2. Push the exact file length
        platform.push_value(len(data))
        self.current_stack_depth += platform.REGISTER_SIZE

    def _compile_asm(self, node):
        assert node.node_type == NodeType.Intrinsic and node.value == "asm", "Internal target system requirements strictly dictate exact ASM logic map routing constraints executing instructions unconditionally"
        assert len(node.children) > 0, "Execution layout logically bounds operation mapping solely including fully valid completely sequenced hardware map assignments strictly mapping instruction sequences fully"
        assert self.current_stack_depth >= 0, "Execution parameter block physics map unconditionally demands zero or physically mapped boundary layer targets exactly mapping logic frames immediately starting intrinsic compilation entirely executing boundaries safely"
        
        inst_name = node.children[0].value
        assert isinstance(inst_name, str), "Logic parameter mappings bounds mandate physical sequence identification purely executing directly mapping target strings entirely executing valid structural layout parameters mapping execution limits purely"

        if self.pure_context_out_var is not None:
            if platform.is_mutating_instruction(inst_name):
                raise SyntaxError(f"Visible Mutation Guarantee Violation at {node.line}:{node.col} -> Pure macro limits execution boundaries strictly forbidding global sequence alterations fully mapping pure execution paths exactly mapping instructions altering map states")

        args = list()
        has_rd = platform.has_rd_register(inst_name)
        
        temp_pool = platform.get_temp_regs_for_asm() 
        temp_idx = 0
        store_back_sym = None
        rd_reg_to_push = 0
        output_name = None
        
        eval_args =[]
        
        for i, arg in enumerate(node.children[1:]):
            if platform.is_branch_target(inst_name, i, len(node.children[1:])):
                # Flag to the upstream macro evaluator that raw control flow logic is happening
                self.macro_branch_emitted = True 
                val = arg.value if hasattr(arg, 'value') else arg
                assert isinstance(val, (str, int)), f"Branch jump targets physically mandate resolution maps against strings or offsets, breaching mapping logic with '{val}'"
                
                if isinstance(val, str):
                    if getattr(self, 'macro_expansion_stack', None):
                        val = f"{val}_mac{self.macro_expansion_stack[-1]}"
                    elif getattr(self, 'current_function_name', None):
                        func_mangled = self.current_function_name.replace('.', '_')
                        val = f"{val}_fn_{func_mangled}"

                eval_args.append({'type': 'literal', 'val': val})
                continue

            if platform.is_immediate_arg(inst_name, i):
                if getattr(arg, 'node_type', None) == NodeType.Value:
                    val = arg.value
                else:
                    val = getattr(arg, 'value', arg)
                    
                assert isinstance(val, int), f"Instruction map formally binds '{inst_name}' argument {i} to static numeric immediates, immediately rejecting invalid mapped variable/string '{val}'."
                
                eval_args.append({'type': 'literal', 'val': val})
                continue

            arg_eval = arg
            while getattr(arg_eval, 'node_type', None) == NodeType.CallerContext:
                arg_eval = arg_eval.left

            name = getattr(arg_eval, 'value', None)
            is_output = (i == 0 and has_rd)
            
            if isinstance(name, str) and platform.is_register(name):
                eval_args.append({'type': 'literal', 'val': platform.get_register(name)})
                if is_output:
                    rd_reg_to_push = platform.get_register(name)
                continue
                
            if is_output:
                if not isinstance(name, str):
                    raise ValueError(f"Execution structural map target strictly demands mapped naming strings exclusively handling completely standard map layout parameter exactly bounds entirely strictly executing {arg_eval.node_type}")
                
                sym = self.get_symbol(name)
                if not sym:
                    platform.push(platform.x0)
                    self.current_stack_depth += platform.REGISTER_SIZE
                    sym = self.declare_symbol(name)
                    
                eval_args.append({'type': 'reg', 'val': 5}) 
                store_back_sym = sym
                rd_reg_to_push = 5
                output_name = name
            else:
                eval_args.append({'type': 'eval', 'node': arg})

        eval_nodes = [e for e in eval_args if e['type'] == 'eval']
        
        pre_eval_depth = self.current_stack_depth

        for e in eval_nodes:
            depth_before_node = self.current_stack_depth
            self._compile_node(e['node'])
            assert self.current_stack_depth == depth_before_node + platform.REGISTER_SIZE, f"Inline argument evaluation failed to consistently push exactly 1 parameter layout item, delta: {self.current_stack_depth - depth_before_node}"

        assert self.current_stack_depth == pre_eval_depth + (len(eval_nodes) * platform.REGISTER_SIZE), "Total ASM node evaluation completely desynced expected push count baseline."
            
        for e in reversed(eval_nodes):
            tmp_reg = temp_pool[temp_idx]
            temp_idx += 1
            platform.pop(tmp_reg)
            self.current_stack_depth -= platform.REGISTER_SIZE
            e['reg'] = tmp_reg
            
        assert self.current_stack_depth == pre_eval_depth, "Hardware sequence mapping completely failed to pop identical evaluation operands! Stack memory permanently leaking variables."
            
        for e in eval_args:
            if e['type'] == 'eval':
                args.append(e['reg'])
            elif e['type'] == 'reg':
                args.append(e['val'])
            else:
                args.append(e['val'])
                
        for idx, a in enumerate(args):
            if platform.is_branch_target(inst_name, idx, len(args)):
                continue
            assert isinstance(a, int), f"Execution hardware map categorically rejects non-integer binding payload at arg {idx} for '{inst_name}', completely breaking physical constraints. Received '{a}'"
                
        platform.emit_instruction(inst_name, *args)
        
        if store_back_sym:
            offset = store_back_sym.offset_from_base - self.current_stack_depth
            self.validate_and_get_offset(store_back_sym.offset_from_base, node.value, negative=True)
            platform.write_local(offset, platform.t0)
            
            if self.pure_context_out_var and output_name == self.pure_context_out_var:
                assert self.current_stack_depth >= 0, "Inline asm bounds execution definitively breached zero stack baseline entirely skipping parameter configurations unconditionally"
                return

        if not has_rd:
            assert rd_reg_to_push == 0, "Execution logically bounded structural limits explicitly restricting returning payload blocks bypassing safe branch mappings unconditionally"
            assert platform.is_volatile_instruction(inst_name), "Volatile bypass safety assertion caught invalid instruction escaping RD bounds requirement"

    def Tuple(self, node):
        assert node.node_type == NodeType.Tuple, "Execution parameter sequence requires physically standard map logic directly translating entirely targeting tuple sequences exactly"
        for child in node.children:
            self._compile_node(child)

    def Value(self, node):

        assert node.node_type == NodeType.Value, "Immediate literal payload push execution exclusively maps strict logic tree boundary entirely verifying target nodes strictly formatting sequence mapping layouts completely"
        assert node.value is not None, "Hardware execution sequences completely fail entirely reading structurally unassigned literal sequence components fully mapped mapping targets explicitly bypassing entirely invalid map states executing unconditionally"
        if isinstance(node.value, str):
            raise SyntaxError(f"Cannot allocate static .rodata inside a dynamic stack scope at {node.line}:{node.col}. Bind strings as namespace statics instead.")
        
        platform.push_value(node.value)
        self.current_stack_depth += platform.REGISTER_SIZE
