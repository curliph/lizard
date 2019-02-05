from pymtl import *

from model.hardware_model import HardwareModel, Result, NotReady
from model.flmodel import FLModel
from core.fl.renametable import RenameTableFL
from util.fl.registerfile import RegisterFileFL
from util.fl.snapshotting_freelist import SnapshottingFreeListFL
from core.rtl.dataflow import PregState, DataFlowManagerInterface
from bitutil import copy_bits


class DataFlowManagerFL(FLModel):

  @HardwareModel.validate
  def __init__(s, dlen, naregs, npregs, nsnapshots, num_src_ports,
               num_dst_ports):
    super(DataFlowManagerFL, s).__init__(
        DataFlowManagerInterface(dlen, naregs, npregs, nsnapshots,
                                 num_src_ports, num_dst_ports))

    s.PregState = PregState(dlen)

    s.snapshot_allocator = SnapshottingFreeListFL(nsnapshots, 1, 1, nsnapshots)
    s.free_regs = SnapshottingFreeListFL(
        npregs - 1,
        num_dst_ports,
        num_src_ports,
        nsnapshots,
        used_slots_initial=naregs - 1)
    arch_used_pregs_reset = [Bits(1, 0) for _ in range(npregs - 1)]
    for i in range(naregs):
      arch_used_pregs_reset[i] = Bits(1, 1)

    s.arch_used_pregs = RegisterFileFL(
        Bits(1),
        npregs - 1,
        0,
        num_dst_ports * 2,
        False,
        True,
        reset_values=arch_used_pregs_reset)

    initial_map = [0] + [x for x in range(naregs - 1)]
    s.rename_table = RenameTableFL(naregs, npregs, num_src_ports, num_dst_ports,
                                   nsnapshots, True, initial_map)
    s.ZERO_TAG = s.rename_table.ZERO_TAG

    preg_reset = [s.PregState() for _ in range(npregs)]
    inverse_reset = [s.interface.Areg for _ in range(npregs)]
    for x in range(naregs - 1):
      preg_reset[x].value = 0
      preg_reset[x].ready = 1
      inverse_reset[x] = x + 1

    s.preg_file = RegisterFileFL(
        s.PregState(),
        npregs,
        num_src_ports,
        num_dst_ports * 2,
        True,
        False,
        reset_values=preg_reset)
    s.inverse = RegisterFileFL(
        s.interface.Areg,
        npregs,
        num_dst_ports,
        num_dst_ports,
        True,
        False,
        reset_values=inverse_reset)
    s.areg_file = RegisterFileFL(
        s.interface.Preg,
        naregs,
        num_dst_ports,
        num_dst_ports,
        False,
        True,
        reset_values=initial_map)

    @s.model_method
    def commit_tag(tag):
      if tag == s.ZERO_TAG:
        return
      old_areg = s.inverse.read(tag).data
      old_preg = s.areg_file.read(old_areg).data
      s.free_regs.free(old_preg)
      s.areg_file.write(addr=old_areg, data=tag)
      s.arch_used_pregs.write(addr=old_preg, data=0)
      s.arch_used_pregs.write(addr=tag, data=1)

    @s.model_method
    def write_tag(tag, value):
      if tag == s.ZERO_TAG:
        return
      new_preg_state = s.PregState()
      new_preg_state.value = value
      new_preg_state.ready = 1
      s.preg_file.write(addr=tag, data=new_preg_state)

    @s.model_method
    def get_src(areg):
      return s.rename_table.lookup(areg).preg

    @s.model_method
    def get_dst(areg):
      if areg == 0:
        return Result(success=1, preg=s.ZERO_TAG)
      allocation = s.free_regs.alloc()
      if isinstance(allocation, NotReady):
        return Result(success=0, preg=0)

      s.rename_table.update(areg=areg, preg=allocation.index)
      new_preg_state = s.PregState()
      new_preg_state.value = 0
      new_preg_state.ready = 0
      s.preg_file.write(addr=allocation.index, data=new_preg_state)
      s.inverse.write(addr=allocation.index, data=areg)

      return Result(success=1, preg=allocation.index)

    @s.model_method
    def read_tag(tag):
      if tag == s.ZERO_TAG:
        return Result(ready=1, value=0)
      else:
        preg_state = s.preg_file.read(addr=tag).data
        return Result(ready=preg_state.ready, value=preg_state.value)

    @s.ready_method
    def snapshot():
      return s.snapshot_allocator.alloc.rdy()

    @s.model_method
    def snapshot():
      id_ = s.snapshot_allocator.alloc().index
      s.snapshot_allocator.reset_alloc_tracking(id_)
      s.free_regs.reset_alloc_tracking(id_)
      s.rename_table.snapshot(id_)
      return id_

    @s.model_method
    def free_snapshot(id_):
      s.snapshot_allocator.free(id_)

    @s.model_method
    def restore(source_id):
      s.snapshot_allocator.revert_allocs(source_id)
      s.free_regs.revert_allocs(source_id)
      s.rename_table.restore(source_id)

    @s.model_method
    def rollback():
      s.snapshot_allocator.set((~Bits(nsnapshots, 0)).uint())
      arch_used_pregs_packed = Bits(npregs - 1, 0)
      arch_used_pregs_dump = s.arch_used_pregs.dump().out
      for i in range(npregs - 1):
        arch_used_pregs_packed[i] = arch_used_pregs_dump[i]
      s.free_regs.set(arch_used_pregs_packed)
      s.rename_table.set(s.areg_file.dump().out)

    @s.model_method
    def read_csr(csr_num):
      return Result(result=0, success=0)

    @s.model_method
    def write_csr(csr_num, value):
      return 0

  def _reset(s):
    s.snapshot_allocator.reset()
    s.free_regs.reset()
    s.arch_used_pregs.reset()
    s.rename_table.reset()
    s.preg_file.reset()
    s.inverse.reset()
    s.areg_file.reset()

  def _snapshot_model_state(s):
    s.snapshot_allocator.snapshot_model_state()
    s.free_regs.snapshot_model_state()
    s.arch_used_pregs.snapshot_model_state()
    s.rename_table.snapshot_model_state()
    s.preg_file.snapshot_model_state()
    s.inverse.snapshot_model_state()
    s.areg_file.snapshot_model_state()

  def _restore_model_state(s, state):
    s.snapshot_allocator.restore_model_state()
    s.free_regs.restore_model_state()
    s.arch_used_pregs.restore_model_state()
    s.rename_table.restore_model_state()
    s.preg_file.restore_model_state()
    s.inverse.restore_model_state()
    s.areg_file.restore_model_state()
