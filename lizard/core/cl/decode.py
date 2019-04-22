from pymtl import *
from lizard.msg.mem import MemMsg4B
from lizard.msg.datapath import *
from lizard.msg.control import *
from lizard.util.cl.ports import InValRdyCLPort, OutValRdyCLPort
from lizard.config.general import *
from lizard.util.line_block import LineBlock
from copy import deepcopy


class DecodeUnitCL(Model):

  def __init__(s, controlflow):
    s.instr_q = InValRdyCLPort(FetchPacket())
    s.decoded_q = OutValRdyCLPort(DecodePacket())

    s.controlflow = controlflow

  def xtick(s):
    if s.reset:
      return

    # Check if frontent being squashed
    redirected = s.controlflow.check_redirect()
    if redirected.valid and not s.instr_q.empty(
    ):  # Squash any waiting fetch packet
      s.instr_q.deq()
      return

    if s.decoded_q.full():
      return

    if s.instr_q.empty():
      return

    fetched = s.instr_q.deq()

    out = DecodePacket()
    copy_fetch_decode(fetched, out)

    inst = fetched.instr
    # Decode it and create packet
    opmap = {
        int(Opcode.OP_IMM): s.dec_op_imm,
        int(Opcode.OP): s.dec_op,
        int(Opcode.SYSTEM): s.dec_system,
        int(Opcode.BRANCH): s.dec_branch,
        int(Opcode.JAL): s.dec_jal,
        int(Opcode.JALR): s.dec_jalr,
        int(Opcode.LUI): s.dec_lui,
        int(Opcode.AUIPC): s.dec_auipc,
        int(Opcode.LOAD): s.dec_load,
        int(Opcode.STORE): s.dec_store,
        int(Opcode.MISC_MEM): s.dec_misc_mem,
        int(Opcode.OP_IMM_32): s.dec_op_imm32,
        int(Opcode.OP_32): s.dec_op_32,
    }

    try:
      opcode = inst[RVInstMask.OPCODE]
      out.opcode = opcode
      opmap[opcode.uint()](inst, out)
    except KeyError as e:
      out.valid = 0
      out.status = PacketStatus.EXCEPTION_TRIGGERED
      out.mcause = ExceptionCode.ILLEGAL_INSTRUCTION
      out.mtval = fetched.instr
    s.decoded_q.enq(out)

  def dec_op_imm(s, inst, res):
    res.rs1 = inst[RVInstMask.RS1]
    res.rs1_valid = 1
    res.rs2_valid = 0
    res.rd = inst[RVInstMask.RD]
    res.rd_valid = 1
    # Mapping from func3 to map of func7_shft64 to shamt instruction
    shamts = {
        0b001: {
            0b0000000: RV64Inst.SLLI,
        },
        0b101: {
            0b000000: RV64Inst.SRLI,
            0b010000: RV64Inst.SRAI,
        },
    }

    nshamts = {
        0b000: RV64Inst.ADDI,
        0b010: RV64Inst.SLTI,
        0b011: RV64Inst.SLTIU,
        0b100: RV64Inst.XORI,
        0b110: RV64Inst.ORI,
        0b111: RV64Inst.ANDI,
    }
    func3 = inst[RVInstMask.FUNCT3].uint()
    func7_shmt = inst[RVInstMask.FUNCT7_SHFT64].uint()
    if (inst[RVInstMask.FUNCT3].uint() in shamts):
      res.instr_d = shamts[func3][func7_shmt]
      res.imm = zext(inst[RVInstMask.SHAMT64], DECODED_IMM_LEN)
    else:
      res.instr_d = nshamts[func3]
      res.imm = sext(inst[RVInstMask.I_IMM], DECODED_IMM_LEN)

    return res

  def dec_op(s, inst, res):
    res.rs1 = inst[RVInstMask.RS1]
    res.rs2 = inst[RVInstMask.RS2]
    res.rd = inst[RVInstMask.RD]
    res.imm = 0
    res.rs1_valid = 1
    res.rs2_valid = 1
    res.rd_valid = 1

    func3 = int(inst[RVInstMask.FUNCT3])
    func7 = int(inst[RVInstMask.FUNCT7])
    insts = {
        (0b000, 0b0000000): RV64Inst.ADD,
        (0b000, 0b0100000): RV64Inst.SUB,
        (0b001, 0b0000000): RV64Inst.SLL,
        (0b010, 0b0000000): RV64Inst.SLT,
        (0b011, 0b0000000): RV64Inst.SLTU,
        (0b100, 0b0000000): RV64Inst.XOR,
        (0b101, 0b0000000): RV64Inst.SRL,
        (0b101, 0b0100000): RV64Inst.SRA,
        (0b110, 0b0000000): RV64Inst.OR,
        (0b111, 0b0000000): RV64Inst.AND,
        (0b000, 0b0000001): RV64Inst.MUL,
        (0b001, 0b0000001): RV64Inst.MULH,
        (0b010, 0b0000001): RV64Inst.MULHSU,
        (0b011, 0b0000001): RV64Inst.MULHU,
        (0b100, 0b0000001): RV64Inst.DIV,
        (0b101, 0b0000001): RV64Inst.DIVU,
        (0b110, 0b0000001): RV64Inst.REM,
        (0b111, 0b0000001): RV64Inst.REMU,
    }
    res.instr_d = insts[(func3, func7)]

    return res

  def dec_op_imm32(s, inst, res):
    res.rs1 = inst[RVInstMask.RS1]
    res.rd = inst[RVInstMask.RD]
    res.imm = 0
    res.rs1_valid = 1
    res.rs2_valid = 0
    res.rd_valid = 1

    if (inst[RVInstMask.FUNCT3] == 0b000):  # Special case for addiw
      res.instr_d = RV64Inst.ADDIW
      res.imm = sext(inst[RVInstMask.I_IMM], DECODED_IMM_LEN)
    else:
      func3 = int(inst[RVInstMask.FUNCT3])
      func7 = int(inst[RVInstMask.FUNCT7])
      insts = {
          (0b001, 0b0000000): RV64Inst.SLLIW,
          (0b101, 0b0000000): RV64Inst.SRLIW,
          (0b101, 0b0100000): RV64Inst.SRAIW,
      }
      res.instr_d = insts[(func3, func7)]
      res.imm = inst[RVInstMask.SHAMT32]
    return res

  def dec_op_32(s, inst, res):
    res.rs1 = inst[RVInstMask.RS1]
    res.rs2 = inst[RVInstMask.RS2]
    res.rd = inst[RVInstMask.RD]
    res.imm = 0
    res.rs1_valid = 1
    res.rs2_valid = 1
    res.rd_valid = 1

    func3 = int(inst[RVInstMask.FUNCT3])
    func7 = int(inst[RVInstMask.FUNCT7])
    insts = {
        (0b000, 0b0000000): RV64Inst.ADDW,
        (0b000, 0b0100000): RV64Inst.SUBW,
        (0b001, 0b0000000): RV64Inst.SLLW,
        (0b101, 0b0000000): RV64Inst.SRLW,
        (0b101, 0b0100000): RV64Inst.SRAW,
        (0b000, 0b0000001): RV64Inst.MULW,
        (0b100, 0b0000001): RV64Inst.DIVW,
        (0b101, 0b0000001): RV64Inst.DIVUW,
        (0b110, 0b0000001): RV64Inst.REMW,
        (0b111, 0b0000001): RV64Inst.REMUW,
    }
    res.instr_d = insts[(func3, func7)]
    return res

  def dec_system(s, inst, res):

    func3 = int(inst[RVInstMask.FUNCT3])
    insts = {
        0b001: RV64Inst.CSRRW,
        0b010: RV64Inst.CSRRS,
        0b011: RV64Inst.CSRRC,
        0b101: RV64Inst.CSRRWI,
        0b110: RV64Inst.CSRRSI,
        0b111: RV64Inst.CSRRCI,
    }

    if func3 in insts:
      res.instr_d = insts[func3]
      if func3 >> 2 == 0:
        res.rs1 = inst[RVInstMask.RS1]
        res.rs1_valid = 1
      else:
        res.imm = zext(inst[RVInstMask.RS1], DECODED_IMM_LEN)
      res.rs2_valid = 0
      res.rd = inst[RVInstMask.RD]
      res.rd_valid = 1

      res.csr = inst[RVInstMask.CSRNUM]
      res.csr_valid = 1

      # if the instruction modifies a CSR, it must be unique:
      # the pipeline must drain before it can issue
      res.unique = 1
    else:
      i_imm = int(inst[RVInstMask.I_IMM])
      insts = {
          0: RV64Inst.ECALL,
          1: RV64Inst.EBREAK,
      }
      res.instr_d = insts[i_imm]

    return res

  def dec_branch(s, inst, res):
    func3 = int(inst[RVInstMask.FUNCT3])
    insts = {
        0b000: RV64Inst.BEQ,
        0b001: RV64Inst.BNE,
        0b100: RV64Inst.BLT,
        0b101: RV64Inst.BGE,
        0b110: RV64Inst.BLTU,
        0b111: RV64Inst.BGEU,
    }

    res.instr_d = insts[func3]

    res.rs1 = inst[RVInstMask.RS1]
    res.rs1_valid = 1
    res.rs2 = inst[RVInstMask.RS2]
    res.rs2_valid = 1
    res.rd_valid = 0

    imm = concat(inst[RVInstMask.B_IMM3], inst[RVInstMask.B_IMM2],
                 inst[RVInstMask.B_IMM1], inst[RVInstMask.B_IMM0], Bits(1, 0))
    res.imm = sext(imm, DECODED_IMM_LEN)

    res.is_control_flow = 1

    return res

  def dec_jal(s, inst, res):
    res.instr_d = RV64Inst.JAL
    res.rd = inst[RVInstMask.RD]
    res.rd_valid = 1
    imm = concat(inst[RVInstMask.J_IMM3], inst[RVInstMask.J_IMM2],
                 inst[RVInstMask.J_IMM1], inst[RVInstMask.J_IMM0], Bits(1, 0))
    res.imm = sext(imm, DECODED_IMM_LEN)

    res.is_control_flow = 1

    return res

  def dec_jalr(s, inst, res):
    res.instr_d = RV64Inst.JALR
    res.rs1 = inst[RVInstMask.RS1]
    res.rs1_valid = 1
    res.rd = inst[RVInstMask.RD]
    res.rd_valid = 1
    imm = inst[RVInstMask.I_IMM]
    res.imm = sext(imm, DECODED_IMM_LEN)

    res.is_control_flow = 1

    return res

  def dec_lui(s, inst, res):
    res.instr_d = RV64Inst.LUI
    res.rd = inst[RVInstMask.RD]
    res.rd_valid = 1
    imm = concat(inst[RVInstMask.U_IMM], Bits(12, 0))
    res.imm = sext(imm, DECODED_IMM_LEN)

    return res

  def dec_auipc(s, inst, res):
    res.instr_d = RV64Inst.AUIPC
    res.rd = inst[RVInstMask.RD]
    res.rd_valid = 1
    imm = concat(inst[RVInstMask.U_IMM], Bits(12, 0))
    res.imm = sext(imm, DECODED_IMM_LEN)

    return res

  def dec_load(s, inst, res):
    funct3 = int(inst[RVInstMask.FUNCT3])
    insts = {
        0b000: RV64Inst.LB,
        0b001: RV64Inst.LH,
        0b010: RV64Inst.LW,
        0b011: RV64Inst.LD,
        0b100: RV64Inst.LBU,
        0b101: RV64Inst.LHU,
        0b110: RV64Inst.LWU,
    }
    res.instr_d = insts[funct3]
    res.funct3 = funct3

    res.rs1 = inst[RVInstMask.RS1]
    res.rs1_valid = 1
    res.rd = inst[RVInstMask.RD]
    res.rd_valid = 1

    res.imm = sext(inst[RVInstMask.I_IMM], DECODED_IMM_LEN)

    return res

  def dec_store(s, inst, res):
    funct3 = int(inst[RVInstMask.FUNCT3])
    insts = {
        0b000: RV64Inst.SB,
        0b001: RV64Inst.SH,
        0b010: RV64Inst.SW,
        0b011: RV64Inst.SD,
    }
    res.instr_d = insts[funct3]
    res.funct3 = funct3

    res.rs1 = inst[RVInstMask.RS1]
    res.rs1_valid = 1
    res.rs2 = inst[RVInstMask.RS2]
    res.rs2_valid = 1

    res.imm = sext(
        concat(inst[RVInstMask.S_IMM1], inst[RVInstMask.S_IMM0]),
        DECODED_IMM_LEN)

    return res

  def dec_misc_mem(s, inst, res):
    funct3 = int(inst[RVInstMask.FUNCT3])
    insts = {
        0b000: RV64Inst.FENCE,
        0b001: RV64Inst.FENCE_I,
    }
    res.instr_d = insts[funct3]
    return res

  def line_trace(s):
    return LineBlock([
        "{}".format(s.decoded_q.msg().pc),
        "{: <8} rd({}): {}".format(
            RV64Inst.name(s.decoded_q.msg().instr_d),
            s.decoded_q.msg().rd_valid,
            s.decoded_q.msg().rd),
        "imm: {}".format(s.decoded_q.msg().imm),
        "rs1({}): {}".format(s.decoded_q.msg().rs1_valid,
                             s.decoded_q.msg().rs1),
        "rs2({}): {}".format(s.decoded_q.msg().rs2_valid,
                             s.decoded_q.msg().rs2),
    ]).validate(s.decoded_q.val())