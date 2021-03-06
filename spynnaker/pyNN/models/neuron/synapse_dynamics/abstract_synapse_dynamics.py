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

import math
import numpy
from six import add_metaclass
from spinn_utilities.abstract_base import (
    AbstractBase, abstractmethod, abstractproperty)


@add_metaclass(AbstractBase)
class AbstractSynapseDynamics(object):

    __slots__ = ()

    NUMPY_CONNECTORS_DTYPE = [("source", "uint32"), ("target", "uint32"),
                              ("weight", "float64"), ("delay", "float64")]

    @abstractmethod
    def is_same_as(self, synapse_dynamics):
        """ Determines if this synapse dynamics is the same as another
        """

    @abstractmethod
    def are_weights_signed(self):
        """ Determines if the weights are signed values
        """

    @abstractmethod
    def get_vertex_executable_suffix(self):
        """ Get the executable suffix for a vertex for this dynamics
        """

    @abstractmethod
    def get_parameters_sdram_usage_in_bytes(self, n_neurons, n_synapse_types):
        """ Get the SDRAM usage of the synapse dynamics parameters in bytes
        """

    @abstractmethod
    def write_parameters(self, spec, region, machine_time_step, weight_scales):
        """ Write the synapse parameters to the spec
        """

    @abstractmethod
    def get_parameter_names(self):
        """ Get the parameter names available from the synapse \
            dynamics components

        :rtype: iterable(str)
        """

    @abstractmethod
    def get_max_synapses(self, n_words):
        """ Get the maximum number of synapses that can be held in the given\
            number of words

        :param n_words: The number of words the synapses must fit in
        :rtype: int
        """

    @abstractproperty
    def changes_during_run(self):
        """ Determine if the synapses change during a run

        :rtype: bool
        """

    def get_provenance_data(self, pre_population_label, post_population_label):
        """ Get the provenance data from this synapse dynamics object
        """
        return list()

    def get_delay_maximum(self, connector, delays):
        """ Get the maximum delay for the synapses
        """
        return connector.get_delay_maximum(delays)

    def get_delay_variance(self, connector, delays):
        """ Get the variance in delay for the synapses
        """
        # pylint: disable=too-many-arguments
        return connector.get_delay_variance(delays)

    def get_weight_mean(self, connector, weights):
        """ Get the mean weight for the synapses
        """
        # pylint: disable=too-many-arguments
        return connector.get_weight_mean(weights)

    def get_weight_maximum(self, connector, weights):
        """ Get the maximum weight for the synapses
        """
        # pylint: disable=too-many-arguments
        return connector.get_weight_maximum(weights)

    def get_weight_variance(self, connector, weights):
        """ Get the variance in weight for the synapses
        """
        # pylint: disable=too-many-arguments
        return connector.get_weight_variance(weights)

    def convert_per_connection_data_to_rows(
            self, connection_row_indices, n_rows, data):
        """ Converts per-connection data generated from connections into\
            row-based data to be returned from get_synaptic_data
        """
        return [
            data[connection_row_indices == i].reshape(-1)
            for i in range(n_rows)]

    def get_n_items(self, rows, item_size):
        """ Get the number of items in each row as 4-byte values, given the\
            item size
        """
        return numpy.array([
            int(math.ceil(float(row.size) / float(item_size)))
            for row in rows], dtype="uint32").reshape((-1, 1))

    def get_words(self, rows):
        """ Convert the row data to words
        """
        words = [numpy.pad(
            row, (0, (4 - (row.size % 4)) & 0x3), mode="constant",
            constant_values=0).view("uint32") for row in rows]
        return words
