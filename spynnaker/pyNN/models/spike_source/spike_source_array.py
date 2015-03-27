from spynnaker.pyNN.buffer_management.storage_objects.buffered_sending_region\
    import BufferedSendingRegion
from spynnaker.pyNN.exceptions import ConfigurationException
from spynnaker.pyNN.models.abstract_models\
    .abstract_population_outgoing_edge_restrictor\
    import AbstractPopulationOutgoingEdgeRestrictor
from spynnaker.pyNN.models.abstract_models.abstract_data_specable_vertex \
    import AbstractDataSpecableVertex
from spynnaker.pyNN.models.spike_source.spike_source_array_partitioned_vertex \
    import SpikeSourceArrayPartitionedVertex
from spynnaker.pyNN.utilities.conf import config
from spynnaker.pyNN.utilities import constants

from pacman.model.partitionable_graph.abstract_partitionable_vertex \
    import AbstractPartitionableVertex
from pacman.model.constraints.tag_allocator_constraints\
    .tag_allocator_require_iptag_constraint\
    import TagAllocatorRequireIptagConstraint

from data_specification.data_specification_generator\
    import DataSpecificationGenerator

from enum import Enum
import logging


logger = logging.getLogger(__name__)


class SpikeSourceArray(AbstractDataSpecableVertex,
                       AbstractPartitionableVertex,
                       AbstractPopulationOutgoingEdgeRestrictor):

    CORE_APP_IDENTIFIER = constants.SPIKE_INJECTOR_CORE_APPLICATION_ID
    _CONFIGURATION_REGION_SIZE = 36

    # limited to the n of the x,y,p,n key format
    _model_based_max_atoms_per_core = 2048

    _SPIKE_SOURCE_REGIONS = Enum(
        value="_SPIKE_SOURCE_REGIONS",
        names=[('SYSTEM_REGION', 0),
               ('CONFIGURATION_REGION', 1),
               ('SPIKE_DATA_REGION', 2)])

    def __init__(
            self, n_neurons, spike_times, machine_time_step, spikes_per_second,
            ring_buffer_sigma, timescale_factor, port=None, tag=None,
            ip_address=None, board_address=None,
            max_on_chip_memory_usage_for_spikes_in_bytes=None,
            constraints=None, label="SpikeSourceArray"):
        if ip_address is None:
            ip_address = config.get("Buffers", "receive_buffer_host")
        if port is None:
            port = config.getint("Buffers", "receive_buffer_port")

        AbstractDataSpecableVertex.__init__(
            self, machine_time_step=machine_time_step,
            timescale_factor=timescale_factor)
        AbstractPartitionableVertex.__init__(
            self, n_atoms=n_neurons, label=label,
            max_atoms_per_core=self._model_based_max_atoms_per_core,
            constraints=constraints)
        AbstractPopulationOutgoingEdgeRestrictor.__init__(self)
        self._spike_times = spike_times
        self._max_on_chip_memory_usage_for_spikes = \
            max_on_chip_memory_usage_for_spikes_in_bytes
        self._threshold_for_reporting_bytes_written = 0

        self.add_constraint(TagAllocatorRequireIptagConstraint(
            ip_address, port, strip_sdp=True, board_address=board_address,
            tag_id=tag))

        if self._max_on_chip_memory_usage_for_spikes is None:
            self._max_on_chip_memory_usage_for_spikes = \
                constants.DEFAULT_MEG_LIMIT

        # check the values do not conflict with chip memory limit
        if (self._max_on_chip_memory_usage_for_spikes >
                constants.MAX_MEG_LIMIT or
                self._max_on_chip_memory_usage_for_spikes < 0):
            raise ConfigurationException(
                "The memory usage on chip is either beyond what is supportable"
                " on the spinnaker board being supported or you have requested"
                " a negative value for a memory usage. Please correct and"
                " try again")

    @property
    def model_name(self):
        """
        Return a string representing a label for this class.
        """
        return "SpikeSourceArray"

    @staticmethod
    def set_model_max_atoms_per_core(new_value):
        SpikeSourceArray.\
            _model_based_max_atoms_per_core = new_value

    def get_regions(self):

        # The buffered region is the spike data region
        return [SpikeSourceArray._SPIKE_SOURCE_REGIONS.SPIKE_DATA_REGION.value]

    def create_subvertex(self, vertex_slice, resources_required, label=None,
                         constraints=list()):
        send_buffer = self._get_spike_send_buffer(vertex_slice)
        partitioned_vertex = SpikeSourceArrayPartitionedVertex(
            {SpikeSourceArray._SPIKE_SOURCE_REGIONS.SPIKE_DATA_REGION.value:
                send_buffer}, resources_required, label, constraints)
        return partitioned_vertex

    def _get_spike_send_buffer(self, vertex_slice):
        """
        spikeArray is a list with one entry per 'neuron'. The entry for
        one neuron is a list of times (in ms) when the neuron fires.
        We need to transpose this 'matrix' and get a list of firing neuron
        indices for each time tick:
        List can come in two formats (both now supported):
        1) Official PyNN format - single list that is used for all neurons
        2) SpiNNaker format - list of lists, one per neuron
        """
        send_buffer = BufferedSendingRegion(
            self._max_on_chip_memory_usage_for_spikes)
        if isinstance(self._spike_times[0], list):

            # This is in SpiNNaker 'list of lists' format:
            for neuron in range(vertex_slice.lo_atom,
                                vertex_slice.hi_atom + 1):
                for timeStamp in sorted(self._spike_times[neuron]):
                    time_stamp_in_ticks = int((timeStamp * 1000.0) /
                                              self._machine_time_step)
                    send_buffer.add_key(time_stamp_in_ticks, neuron)
        else:

            # This is in official PyNN format, all neurons use the same list:
            neuron_list = range(vertex_slice.lo_atom, vertex_slice.hi_atom + 1)
            for timeStamp in sorted(self._spike_times):
                time_stamp_in_ticks = int((timeStamp * 1000.0) /
                                          self._machine_time_step)

                # add to send_buffer collection
                send_buffer.add_keys(time_stamp_in_ticks, neuron_list)
        return send_buffer

    def _reserve_memory_regions(self, spec, spike_region_size):
        """
        *** Modified version of same routine in models.py These could be
        combined to form a common routine, perhaps by passing a list of
        entries. ***
        Reserve memory for the system, indices and spike data regions.
        The indices region will be copied to DTCM by the executable.
        """
        spec.reserve_memory_region(
            region=self._SPIKE_SOURCE_REGIONS.SYSTEM_REGION.value,
            size=12, label='systemInfo')

        spec.reserve_memory_region(
            region=self._SPIKE_SOURCE_REGIONS.CONFIGURATION_REGION.value,
            size=self._CONFIGURATION_REGION_SIZE, label='configurationRegion')

        spec.reserve_memory_region(
            region=self._SPIKE_SOURCE_REGIONS.SPIKE_DATA_REGION.value,
            size=spike_region_size, label='SpikeDataRegion', empty=True)

    def _write_setup_info(self, spec, spike_buffer_region_size, ip_tags):
        """
        Write information used to control the simulation and gathering of
        results. Currently, this means the flag word used to signal whether
        information on neuron firing and neuron potential is either stored
        locally in a buffer or passed out of the simulation for storage/display
        as the simulation proceeds.

        The format of the information is as follows:
        Word 0: Flags selecting data to be gathered during simulation.
            Bit 0: Record spike history
            Bit 1: Record neuron potential
            Bit 2: Record gsyn values
            Bit 3: Reserved
            Bit 4: Output spike history on-the-fly
            Bit 5: Output neuron potential
            Bit 6: Output spike rate
        """
        # What recording commands were set for the parent pynn_population.py?
        self._write_basic_setup_info(spec,
                                     SpikeSourceArray.CORE_APP_IDENTIFIER)

        # add the params saying how big each
        spec.switch_write_focus(
            region=self._SPIKE_SOURCE_REGIONS.CONFIGURATION_REGION.value)

        # write configs for reverse ip tag
        # NOTE
        # as the packets are formed in the buffers, and that its a spike source
        # array, and shouldn't have injected packets, no config should be
        # required for it to work. the packet format will override these anyhow
        # END NOTE
        spec.write_value(data=0)  # prefix value
        spec.write_value(data=0)  # prefix
        spec.write_value(data=0)  # key left shift
        spec.write_value(data=0)  # add key check
        spec.write_value(data=0)  # key for transmitting
        spec.write_value(data=0)  # mask for transmitting

        # write configs for buffers
        spec.write_value(data=spike_buffer_region_size)
        spec.write_value(data=self._threshold_for_reporting_bytes_written)

        ip_tag = iter(ip_tags).next()
        spec.write_value(data=ip_tag.tag)

    # inherited from dataspecable vertex
    def generate_data_spec(self, subvertex, placement, subgraph, graph,
                           routing_info, hostname, graph_mapper, report_folder,
                           ip_tags, reverse_ip_tags):
        """
        Model-specific construction of the data blocks necessary to build a
        single SpikeSource Array on one core.
        """
        data_writer, report_writer = \
            self.get_data_spec_file_writers(
                placement.x, placement.y, placement.p, hostname, report_folder)

        spec = DataSpecificationGenerator(data_writer, report_writer)

        spec.comment("\n*** Spec for SpikeSourceArray Instance ***\n\n")

        # ###################################################################
        # Reserve SDRAM space for memory areas:

        spec.comment("\nReserving memory space for spike data region:\n\n")

        # Create the data regions for the spike source array:
        self._reserve_memory_regions(
            spec, self._max_on_chip_memory_usage_for_spikes)

        self._write_setup_info(
            spec, self._max_on_chip_memory_usage_for_spikes, ip_tags)

        # End-of-Spec:
        spec.end_specification()
        data_writer.close()

    def get_binary_file_name(self):
        return "reverse_iptag_multicast_source.aplx"

    # inherited from partitionable vertex
    def get_cpu_usage_for_atoms(self, vertex_slice, graph):
        """ assumed correct cpu usage is not important

        :param vertex_slice:
        :param graph:
        :return:
        """
        return 0

    def get_sdram_usage_for_atoms(self, vertex_slice, vertex_in_edges):
        """ calculates the total sdram usage of the spike source array. If the
        memory requirement is beyond what is deemed to be the usage of the
        processor, then it executes a buffered format.

        :param vertex_slice:
        :param vertex_in_edges:
        :return:
        """
        return constants.SETUP_SIZE + self._max_on_chip_memory_usage_for_spikes

    def get_dtcm_usage_for_atoms(self, vertex_slice, graph):
        """ assumed that correct dtcm usage is not required

        :param vertex_slice:
        :param graph:
        :return:
        """
        return 0
