
def sign_extend(val, bits):
    if val & (1 << (bits - 1)):
        return val - (1 << bits)
    return val

def disassemble(bytecode):
    inst_map = {}
    for i in range(0, len(bytecode), 4):
        if i + 4 > len(bytecode): 
            break
        
        inst = int.from_bytes(bytecode[i:i+4], 'little')
        opcode = inst & 0x7F
        rd = (inst >> 7) & 0x1F
        rs1 = (inst >> 15) & 0x1F
        rs2 = (inst >> 20) & 0x1F
        funct3 = (inst >> 12) & 0x7
        funct7 = (inst >> 25) & 0x7F
        
        out = f"0x{i:04x}: {inst:08x}    "
        
        if opcode == 0x13: # I-Type
            imm = sign_extend((inst >> 20) & 0xFFF, 12)
            if funct3 == 5:
                op = "srai" if (inst >> 30) & 1 else "srli"
                imm = imm & 0x1F 
            else:
                op = {0:"addi", 1:"slli", 2:"slti", 3:"sltiu", 4:"xori", 6:"ori", 7:"andi"}.get(funct3, f"op_imm_{funct3}")
                if funct3 == 1:
                    imm = imm & 0x1F
            out += f"{op:<5} x{rd}, x{rs1}, {imm}"
            
        elif opcode == 0x33: # R-Type
            op = "unknown"
            if funct3 == 0: op = "sub" if funct7 == 0x20 else "add"
            elif funct3 == 1: op = "sll"
            elif funct3 == 2: op = "slt"
            elif funct3 == 3: op = "sltu"
            elif funct3 == 4: op = "xor"
            elif funct3 == 5: op = "sra" if funct7 == 0x20 else "srl"
            elif funct3 == 6: op = "or"
            elif funct3 == 7: op = "and"
            out += f"{op:<5} x{rd}, x{rs1}, x{rs2}"
            
        elif opcode == 0x03: # Load
            imm = sign_extend((inst >> 20) & 0xFFF, 12)
            op = {2:"lw", 4:"lbu"}.get(funct3, "load")
            out += f"{op:<5} x{rd}, {imm}(x{rs1})"
            
        elif opcode == 0x23: # Store
            imm = sign_extend(((inst >> 25) << 5) | ((inst >> 7) & 0x1F), 12)
            op = {0:"sb", 2:"sw"}.get(funct3, "store")
            out += f"{op:<5} x{rs2}, {imm}(x{rs1})"
            
        elif opcode == 0x6F: # JAL
            imm = ((inst >> 31) << 20) | (((inst >> 12) & 0xFF) << 12) | (((inst >> 20) & 1) << 11) | (((inst >> 21) & 0x3FF) << 1)
            imm = sign_extend(imm, 21)
            out += f"jal   x{rd}, {imm} (-> 0x{i + imm:04x})"
            
        elif opcode == 0x67: # JALR (and RET)
            imm = sign_extend((inst >> 20) & 0xFFF, 12)
            if rd == 0 and rs1 == 1 and imm == 0:
                out += f"ret"
            else:
                out += f"jalr  x{rd}, x{rs1}, {imm}"
                
        elif opcode == 0x63: # Branch
            imm = ((inst >> 31) << 12) | (((inst >> 7) & 1) << 11) | (((inst >> 25) & 0x3F) << 5) | (((inst >> 8) & 0xF) << 1)
            imm = sign_extend(imm, 13)
            op = "beq" if funct3 == 0 else "bne" if funct3 == 1 else "bge" if funct3 == 5 else "b_cond"
            out += f"{op:<5} x{rs1}, x{rs2}, {imm} (-> 0x{i + imm:04x})"
            
        elif opcode == 0x37: # LUI
            imm = (inst >> 12) & 0xFFFFF
            out += f"lui   x{rd}, 0x{imm:05x}"
            
        elif opcode == 0x73:
            out += "ecall"
            
        else:
            out += f"??? (opcode 0x{opcode:02x})"
        inst_map[i] = out
    return inst_map
            