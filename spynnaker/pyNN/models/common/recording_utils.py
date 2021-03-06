# Copyright (c) 2017-2019 The University of Manchester
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import division
import logging
import struct
import numpy
from spinn_front_end_common.utilities.helpful_functions import (
    locate_memory_region_for_placement)
from spynnaker.pyNN.exceptions import MemReadException

logger = logging.getLogger(__name__)
_RECORDING_COUNT = struct.Struct("<I")


def get_recording_region_size_in_bytes(
        n_machine_time_steps, bytes_per_timestep):
    """ Get the size of a recording region in bytes
    """
    if n_machine_time_steps is None:
        raise Exception(
            "Cannot record this parameter without a fixed run time")
    return ((n_machine_time_steps * bytes_per_timestep) +
            (n_machine_time_steps * 4))


def get_data(transceiver, placement, region, region_size):
    """ Get the recorded data from a region
    """

    region_base_address = locate_memory_region_for_placement(
        placement, region, transceiver)
    number_of_bytes_written = _RECORDING_COUNT.unpack_from(
        transceiver.read_memory(
            placement.x, placement.y, region_base_address,
            _RECORDING_COUNT.size))[0]

    # Subtract 4 for the word representing the size itself
    expected_size = region_size - _RECORDING_COUNT.size
    if number_of_bytes_written > expected_size:
        raise MemReadException(
            "Expected {} bytes but read {}".format(
                expected_size, number_of_bytes_written))

    return (
        transceiver.read_memory(
            placement.x, placement.y, region_base_address + 4,
            number_of_bytes_written),
        number_of_bytes_written)


def pull_off_cached_lists(no_loads, cache_file):
    """ Extracts numpy based data from a  file

    :param no_loads: the number of numpy elements in the file
    :param cache_file: the file to extract from
    :return: The extracted data
    """
    cache_file.seek(0)
    if no_loads == 1:
        values = numpy.load(cache_file)
        # Seek to the end of the file (for windows compatibility)
        cache_file.seek(0, 2)
        return values
    elif no_loads == 0:
        return []

    lists = list()
    for _ in range(0, no_loads):
        lists.append(numpy.load(cache_file))
    # Seek to the end of the file (for windows compatibility)
    cache_file.seek(0, 2)
    return numpy.concatenate(lists)


def needs_buffering(buffer_max, space_needed, enable_buffered_recording):
    if space_needed == 0:
        return False
    if not enable_buffered_recording:
        return False
    if buffer_max < space_needed:
        return True
    return False


def get_buffer_sizes(buffer_max, space_needed, enable_buffered_recording):
    if space_needed == 0:
        return 0
    if not enable_buffered_recording:
        return space_needed
    if buffer_max < space_needed:
        return buffer_max
    return space_needed


def make_missing_string(missing):
    missing_str = ""
    separator = ""
    for placement in missing:
        missing_str += "{}({}, {}, {})".format(
            separator, placement.x, placement.y, placement.p)
        separator = "; "
    return missing_str
