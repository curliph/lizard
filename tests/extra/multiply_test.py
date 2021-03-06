from pymtl import *
from tests.context import lizard
from lizard.util.rtl.multiply import MulPipelined, MulPipelinedInterface, MulRetimedPipelined
from lizard.util.cl.multiply import MulCL
from tests.config import test_verilog
from lizard.util.test_utils import run_model_translation, run_test_vector_sim
from lizard.model.test_model import run_test_state_machine
from lizard.model.wrapper import wrap_to_rtl, wrap_to_cl


#Create a single instance of an issue slot
def test_translation():
  iface = MulPipelinedInterface(64)
  run_model_translation(MulRetimedPipelined(iface, 4))
  run_model_translation(MulPipelined(iface, 4, True))
  run_model_translation(MulPipelined(iface, 4, False))


#
#
# # Create a single instance of an issue slot
# def test_basic():
#   iface = MulPipelinedInterface(8, keep_upper=True)
#   #mult = MulPipelined(iface, 1)
#   mult = MulPipelined(iface, 4)
#   mult.vcd_file = 'foo.vcd'
#   dut = wrap_to_cl(mult)
#   dut.reset()
#
#   #print(dut.result())
#   print(dut.mult(src1=0xff, src2=0xff, signed=False))
#   dut.cycle()
#   dut.cycle()
#   dut.cycle()
#   dut.cycle()
#   print(dut.peek())
#   dut.cycle()
#
#
# def test_fail():
#   iface = MulPipelinedInterface(8)
#   #mult = MulPipelined(iface, 1)
#   mult = MulPipelined(iface, 4)
#   dut = wrap_to_cl(mult)
#   dut.reset()
#   dut.cycle()
#   print(dut.mult(signed=0, src1=0, src2=0))
#   dut.cycle()
#   print(dut.mult(signed=0, src1=1, src2=1))
#   dut.cycle()
#   print(dut.mult(signed=0, src1=0, src2=0))
#   dut.cycle()
#   dut.cycle()
#   print(dut.mult(signed=0, src1=0, src2=0))
#   dut.cycle()
#   print(dut.result())
#   dut.cycle()
#   print(dut.result())
#   dut.cycle()
#
#
# def test_fail2():
#   iface = MulPipelinedInterface(64)
#   #mult = MulPipelined(iface, 1)
#   mult = MulPipelined(iface, 4, use_mul=True)
#   #mult = MulRetimedPipelined(iface, 4)
#   mult.vcd_file = 'mult.vcd'
#   dut = wrap_to_cl(mult)
#   dut.reset()
#   dut.cycle()
#   print(dut.mult(signed=0, src1=0, src2=0))
#   dut.cycle()
#   print(dut.mult(signed=0, src1=0, src2=0))
#   dut.cycle()
#   print(dut.mult(signed=0, src1=0, src2=0))
#   dut.cycle()
#   print(dut.mult(signed=0, src1=1, src2=1))
#   dut.cycle()
#   assert dut.result().res == 0
#   dut.cycle()
#   assert dut.result().res == 0
#   dut.cycle()
#   assert dut.result().res == 0
#   dut.cycle()
#   assert dut.result().res == 1
#   dut.cycle()


def test_fail3():
  iface = MulPipelinedInterface(64)
  #mult = MulPipelined(iface, 1)
  mult = MulPipelined(iface, 4, use_mul=True)
  #mult = MulRetimedPipelined(iface, 4)
  mult.vcd_file = 'mult.vcd'
  dut = wrap_to_cl(mult)

  def peek_tk_mult_cycle(x, tup):
    if x is not None:
      print(dut.peek().res)
      assert dut.peek().res == 0
      dut.take()
    if tup is not None:
      print(tup[0])
      dut.mult(src1_signed=tup[0], src2_signed=tup[0], src1=tup[1], src2=tup[2])
    dut.cycle()

  dut.reset()

  peek_tk_mult_cycle(None, (0, 2, 1))
  dut.cycle()
  dut.cycle()
  dut.cycle()
  # peek_tk_mult_cycle(None, (0,0,0))
  # peek_tk_mult_cycle(None, (0,0,0))
  # peek_tk_mult_cycle(None, (0,2,1))
  # peek_tk_mult_cycle(0, None)
  # peek_tk_mult_cycle(0, None)
  # peek_tk_mult_cycle(0, None)
  assert dut.peek().res == 2
  #peek_tk_mult_cycle(2, None)


def test_state_machine():
  run_test_state_machine(MulPipelined, MulCL, (MulPipelinedInterface(64), 4))


def test_state_machine_single_cycle():
  run_test_state_machine(MulPipelined, MulCL, (MulPipelinedInterface(64), 1))


def test_state_machine2():
  run_test_state_machine(MulRetimedPipelined, MulCL,
                         (MulPipelinedInterface(64), 4))
