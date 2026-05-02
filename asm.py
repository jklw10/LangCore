import struct

class RiscVAssembler:
    REGISTER_SIZE = 4 
    def __init__(self):
        self.code = bytearray()
        self.labels = {}
        self.fixups = {}
        self.pc = 0

    def get_binary(self):
        if self.fixups:
            remaining = list(self.fixups.keys())
            raise ValueError(f"Undefined label(s): {remaining}")
        return bytes(self.code)
    def _emit(self, val):
        self.code.extend(struct.pack("<I", val))
    
    def label(self, name):
        current_pc = len(self.code)
        
        if name in self.labels:
            raise ValueError(f"Label '{name}' defined twice")
        
        self.labels[name] = current_pc
        
        if name in self.fixups:
            for addr, i_type in self.fixups[name]:
                offset = current_pc - addr
                
                if i_type == 'J':
                    scrambled_imm = self._encode_j_imm(offset)
                elif i_type == 'B':
                    scrambled_imm = self._encode_b_imm(offset)
                
                old_inst = struct.unpack_from("<I", self.code, addr)[0]
                new_inst = old_inst | scrambled_imm
                struct.pack_into("<I", self.code, addr, new_inst)
            
            del self.fixups[name]

    def _resolve_or_record(self, label, i_type):
        current_pc = len(self.code)
        
        if isinstance(label, int): 
            return label

        if label in self.labels:
            return self.labels[label] - current_pc

        if label not in self.fixups:
            self.fixups[label] = []
        
        self.fixups[label].append((current_pc, i_type))
        return 0 

    def _r_type(self, opcode, rd, rs1, rs2, funct3, funct7):
        inst = (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode
        self._emit(inst)

    def _i_type(self, opcode, rd, rs1, imm, funct3):
        imm = imm & 0xFFF 
        inst = (imm << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode
        self._emit(inst)

    def _s_type(self, opcode, rs1, rs2, imm, funct3):
        imm = imm & 0xFFF
        imm_11_5 = (imm >> 5) & 0x7F
        imm_4_0 = imm & 0x1F
        inst = (imm_11_5 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (imm_4_0 << 7) | opcode
        self._emit(inst)
    
    def _j_type(self, opcode, rd, offset):
        return self._encode_j_imm(offset) | (rd << 7) | opcode

    def _b_type(self, opcode, rs1, rs2, offset, funct3):
        return self._encode_b_imm(offset) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | opcode

    # --- Immediate Arithmetic ---
    def addi(self, rd, rs1, imm): 
        self._i_type(0x13, rd, rs1, imm, 0x0)
        
    def xori(self, rd, rs1, imm): 
        self._i_type(0x13, rd, rs1, imm, 0x4)
        
    def ori(self,  rd, rs1, imm): 
        self._i_type(0x13, rd, rs1, imm, 0x6)
        
    def andi(self, rd, rs1, imm): 
        self._i_type(0x13, rd, rs1, imm, 0x7)
        
    def sltiu(self, rd, rs1, imm):
        """rd = (rs1 < imm) ? 1 : 0 (unsigned)"""
        self._i_type(0x13, rd, rs1, imm, 0x3)
    
    # --- Register Arithmetic ---
    def add(self, rd, rs1, rs2): 
        self._r_type(0x33, rd, rs1, rs2, 0x0, 0x00)
        
    def sub(self, rd, rs1, rs2): 
        self._r_type(0x33, rd, rs1, rs2, 0x0, 0x20)
        
    def xor(self, rd, rs1, rs2): 
        self._r_type(0x33, rd, rs1, rs2, 0x4, 0x00)
        
    def or_(self, rd, rs1, rs2): 
        self._r_type(0x33, rd, rs1, rs2, 0x6, 0x00)
        
    def and_(self,rd, rs1, rs2): 
        self._r_type(0x33, rd, rs1, rs2, 0x7, 0x00)

    def sltu(self, rd, rs1, rs2):
        """rd = (rs1 < rs2) ? 1 : 0 (unsigned)"""
        self._r_type(0x33, rd, rs1, rs2, 0x3, 0x00)
        
    def slt(self, rd, rs1, rs2):
        """rd = (rs1 < rs2) ? 1 : 0 (signed)"""
        self._r_type(0x33, rd, rs1, rs2, 0x2, 0x00)

    # --- Memory Access ---
    def load(self, rd, rs1, offset): 
        self._i_type(0x03, rd, rs1, offset, 0x2)
        
    def store(self, rs1, offset, rs2): 
        self._s_type(0x23, rs1, rs2, offset, 0x2) 
    
    def lw(self, rd, rs1, offset): 
        self._i_type(0x03, rd, rs1, offset, 0x2)
        
    def sw(self, rs1, offset, rs2): 
        self._s_type(0x23, rs1, rs2, offset, 0x2) 

    def lbu(self, rd, rs1, offset):
        self._i_type(0x03, rd, rs1, offset, 0x4)
        
    def sb(self, rs1, offset, rs2):
        self._s_type(0x23, rs1, rs2, offset, 0x0)
    # --- Branching ---
    def jal(self, rd, label):
        offset = self._resolve_or_record(label, 'J')
        inst = self._j_type(0x6F, rd, offset)
        self.code.extend(struct.pack("<I", inst))

    def jalr(self, rd, rs1, offset):
        self._i_type(0x67, rd, rs1, offset, 0x0)
        
    def bge(self, rs1, rs2, label):
        offset = self._resolve_or_record(label, 'B')
        inst = self._b_type(0x63, rs1, rs2, offset, 0x5)
        self.code.extend(struct.pack("<I", inst))

    def beq(self, rs1, rs2, label):
        offset = self._resolve_or_record(label, 'B')
        inst = self._b_type(0x63, rs1, rs2, offset, 0x0)
        self.code.extend(struct.pack("<I", inst))
    
    def bne(self, rs1, rs2, label): 
        offset = self._resolve_or_record(label, 'B')
        inst = self._b_type(0x63, rs1, rs2, offset, 0x1)
        self.code.extend(struct.pack("<I", inst))
    
    def lui(self, rd, imm):
        opcode = 0x37
        imm_val = (int(imm) & 0xFFFFF)
        inst = (imm_val << 12) | (rd << 7) | opcode
        self.code.extend(struct.pack("<I", inst))

    def _encode_j_imm(self, offset):
        imm = int(offset) & 0x1FFFFF 
        bit_20 = (imm >> 20) & 1
        bits_19_12 = (imm >> 12) & 0xFF
        bit_11 = (imm >> 11) & 1
        bits_10_1 = (imm >> 1) & 0x3FF
        return (bit_20 << 31) | (bits_10_1 << 21) | (bit_11 << 20) | (bits_19_12 << 12)

    def _encode_b_imm(self, offset):
        imm = int(offset) & 0x1FFF 
        bit_12 = (imm >> 12) & 1
        bit_11 = (imm >> 11) & 1
        bits_10_5 = (imm >> 5) & 0x3F
        bits_4_1 = (imm >> 1) & 0xF
        return (bit_12 << 31) | (bits_10_5 << 25) | (bits_4_1 << 8) | (bit_11 << 7)

    def ecall(self): 
        self._emit(0x00000073)