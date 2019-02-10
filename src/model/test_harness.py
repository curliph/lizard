from pymtl import *
from util.rtl.interface import Interface, IncludeAll, UseInterface, connect_m
from model.translate import translate


def TestHarness(target, dut, translate_model, vcd_file=''):
  test_harness_interface = Interface([], bases=[IncludeAll(dut.interface)])
  UseInterface(target, test_harness_interface)

  if translate_model:
    dut.vcd_file = vcd_file
    target.dut = translate(dut)
  else:
    target.dut = dut

  for name in target.interface.methods.keys():
    connect_m(getattr(target, name), getattr(target.dut, name))

  target.vcd_file = vcd_file