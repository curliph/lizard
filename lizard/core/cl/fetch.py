from pymtl import *
from lizard.msg.mem import MemMsg8B
from lizard.msg.datapath import *
from lizard.msg.control import *
from lizard.util.cl.ports import InValRdyCLPort, OutValRdyCLPort
from lizard.config.general import *
from lizard.util.line_block import LineBlock
from copy import deepcopy


class FetchUnitCL(Model):

  def __init__(s, controlflow):
    s.req_q = OutValRdyCLPort(MemMsg8B.req)
    s.resp_q = InValRdyCLPort(MemMsg8B.resp)
    s.instrs_q = OutValRdyCLPort(FetchPacket())

    s.in_flight = Wire(1)
    s.drop_mem = Wire(1)

    s.pc = Wire(XLEN)
    s.pc_in_flight = Wire(XLEN)

    s.controlflow = controlflow

  def xtick(s):
    if s.reset:
      s.drop_mem = False
      s.in_flight = False

    # Check if the controlflow is redirecting the front end
    redirected = s.controlflow.check_redirect()
    if redirected.valid:  # Squash everything
      # drop any mem responses
      if (not s.resp_q.empty()):
        s.resp_q.deq()
        s.in_flight = False
      else:
        s.drop_mem = s.in_flight
      # Redirect PC
      s.pc.next = redirected.target
      return

    # Drop unit
    if s.drop_mem and not s.resp_q.empty():
      s.resp_q.deq()
      s.drop_mem = False
      s.in_flight = False

    # We got a memresp
    if not s.resp_q.empty() and not s.instrs_q.full():
      mem_resp = s.resp_q.deq()
      out = FetchPacket()
      out.status = PacketStatus.ALIVE
      out.instr = mem_resp.data
      out.pc = s.pc_in_flight
      out.pc_next = s.pc
      s.instrs_q.enq(out)
      s.in_flight = False

    if not s.in_flight:  # We can send next request
      s.req_q.enq(MemMsg8B.req.mk_rd(0, s.pc, ILEN_BYTES))
      s.in_flight = True
      s.pc_in_flight.next = s.pc
      #TODO insert btb here, so easy!
      s.pc.next = s.pc + ILEN_BYTES

  def line_trace(s):
    return LineBlock([
        'pc: {}'.format(s.instrs_q.msg().pc),
    ]).validate(s.instrs_q.val())