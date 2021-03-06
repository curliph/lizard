#=========================================================================
# elf_test.py
#=========================================================================

from lizard.util import elf
import os
import random
import struct

from lizard.util.sparse_memory_image import SparseMemoryImage

#-------------------------------------------------------------------------
# test_basic
#-------------------------------------------------------------------------


def test_basic(tmpdir):

  # Create a sparse memory image

  mem_image = SparseMemoryImage()

  section_names = [".text", ".data"]

  for i in xrange(4):

    name = section_names[random.randint(0, 1)]
    addr = i * 0x00000200

    data_ints = [random.randint(0, 1000) for r in xrange(10)]
    data_bytes = bytearray()
    for data_int in data_ints:
      data_bytes.extend(struct.pack("<I", data_int))

    data = data_bytes

    mem_image.add_section(name, addr, data)

  # Write the sparse memory image to an ELF file

  with tmpdir.join("elf-test").open('wb') as file_obj:
    elf.elf_writer(mem_image, file_obj)

  # Read the ELF file back into a new sparse memory image

  mem_image_test = None
  with tmpdir.join("elf-test").open('rb') as file_obj:
    mem_image_test = elf.elf_reader(file_obj)

  # Check that the original and new sparse memory images are equal

  assert sorted(mem_image.sections.keys()) == sorted(
      mem_image_test.sections.keys())
  for key in mem_image.sections.keys():
    expected = mem_image[key]
    test = mem_image_test[key]
    assert expected.addr == test.addr
    assert expected.data == test.data
