import numpy as np
from nomadcore.simple_parser import SimpleMatcher as SM
from nomadcore.baseclasses import MainHierarchicalParser
from commonmatcher import CommonMatcher
import cp2kparser.generic.configurationreading
import cp2kparser.generic.csvparsing
from nomadcore.caching_backend import CachingLevel
import logging
logger = logging.getLogger("nomad")


#===============================================================================
class CP2KMDParser(MainHierarchicalParser):
    """Used to parse the CP2K calculation with run types:
        -MD
        -MOLECULAR_DYNAMICS
    """
    def __init__(self, file_path, parser_context):
        """
        """
        super(CP2KMDParser, self).__init__(file_path, parser_context)
        self.setup_common_matcher(CommonMatcher(parser_context))
        self.traj_iterator = None
        self.energy_iterator = None
        self.n_steps = None
        self.output_freq = None
        self.coord_freq = None
        self.velo_freq = None
        self.energy_freq = None

        #=======================================================================
        # Globally cached values
        self.cache_service.add_cache_object("number_of_frames_in_sequence", 0)
        self.cache_service.add_cache_object("frame_sequence_potential_energy", [])
        self.cache_service.add_cache_object("frame_sequence_local_frames_ref", [])

        #=======================================================================
        # Cache levels
        self.caching_level_for_metaname.update({
            'x_cp2k_section_md_settings': CachingLevel.ForwardAndCache,
            'x_cp2k_section_md_step': CachingLevel.ForwardAndCache,
            'x_cp2k_section_quickstep_calculation': CachingLevel.ForwardAndCache,
            "x_cp2k_section_scf_iteration": CachingLevel.ForwardAndCache,
            "x_cp2k_section_stress_tensor": CachingLevel.ForwardAndCache,
        })

        #=======================================================================
        # SimpleMatchers
        self.md = SM(
            " MD\| Molecular Dynamics Protocol",
            forwardMatch=True,
            sections=["section_frame_sequence", "x_cp2k_section_md"],
            subMatchers=[
                SM( " MD\| Molecular Dynamics Protocol",
                    forwardMatch=True,
                    sections=["x_cp2k_section_md_settings"],
                    subMatchers=[
                        SM( " MD\| Ensemble Type\s+(?P<x_cp2k_md_ensemble_type>{})".format(self.cm.regex_word)),
                        SM( " MD\| Number of Time Steps\s+(?P<x_cp2k_md_number_of_time_steps>{})".format(self.cm.regex_i)),
                        SM( " MD\| Time Step \[fs\]\s+(?P<x_cp2k_md_time_step__fs>{})".format(self.cm.regex_f)),
                        SM( " MD\| Temperature \[K\]\s+(?P<x_cp2k_md_temperature>{})".format(self.cm.regex_f)),
                        SM( " MD\| Temperature tolerance \[K\]\s+(?P<x_cp2k_md_temperature_tolerance>{})".format(self.cm.regex_f)),
                        SM( " MD\| Print MD information every\s+(?P<x_cp2k_md_print_frequency>{}) step\(s\)".format(self.cm.regex_i)),
                        SM( " MD\| File type     Print frequency\[steps\]                             File names"),
                        SM( " MD\| Coordinates\s+(?P<x_cp2k_md_coordinates_print_frequency>{})\s+(?P<x_cp2k_md_coordinates_filename>{})".format(self.cm.regex_i, self.cm.regex_word)),
                        SM( " MD\| Velocities\s+(?P<x_cp2k_md_velocities_print_frequency>{})\s+(?P<x_cp2k_md_velocities_filename>{})".format(self.cm.regex_i, self.cm.regex_word)),
                        SM( " MD\| Energies\s+(?P<x_cp2k_md_energies_print_frequency>{})\s+(?P<x_cp2k_md_energies_filename>{})".format(self.cm.regex_i, self.cm.regex_word)),
                        SM( " MD\| Dump\s+(?P<x_cp2k_md_dump_print_frequency>{})\s+(?P<x_cp2k_md_dump_filename>{})".format(self.cm.regex_i, self.cm.regex_word)),
                    ]
                ),
                SM( " ************************** Velocities initialization **************************".replace("*", "\*"),
                    name="md_initialization_step",
                    endReStr=" INITIAL CELL ANGLS",
                    sections=["x_cp2k_section_md_step"],
                    subMatchers=[
                        self.cm.quickstep_calculation(),
                        SM( " ******************************** GO CP2K GO! **********************************".replace("*", "\*")),
                        SM( " INITIAL POTENTIAL ENERGY\[hartree\]     =\s+(?P<x_cp2k_md_potential_energy_instantaneous__hartree>{})".format(self.cm.regex_f)),
                        SM( " INITIAL KINETIC ENERGY\[hartree\]       =\s+(?P<x_cp2k_md_kinetic_energy_instantaneous__hartree>{})".format(self.cm.regex_f)),
                        SM( " INITIAL TEMPERATURE\[K\]                =\s+(?P<x_cp2k_md_temperature_instantaneous>{})".format(self.cm.regex_f)),
                        SM( " INITIAL VOLUME\[bohr\^3\]                =\s+(?P<x_cp2k_md_volume__bohr3>{})".format(self.cm.regex_f)),
                    ],
                ),
                SM( " SCF WAVEFUNCTION OPTIMIZATION",
                    endReStr=" TEMPERATURE \[K\]              =",
                    name="md_step",
                    repeats=True,
                    sections=["x_cp2k_section_md_step"],
                    subMatchers=[
                        self.cm.quickstep_calculation(),
                        SM( " ENSEMBLE TYPE                ="),
                        SM( " STEP NUMBER                  ="),
                        SM( " TIME \[fs\]                    =\s+(?P<x_cp2k_md_time__fs>{})".format(self.cm.regex_f)),
                        SM( " CONSERVED QUANTITY \[hartree\] =\s+(?P<x_cp2k_md_conserved_quantity__hartree>{})".format(self.cm.regex_f)),
                        SM( " CPU TIME \[s\]                 =\s+(?P<x_cp2k_md_cpu_time_instantaneous>{})\s+(?P<x_cp2k_md_cpu_time_average>{})".format(self.cm.regex_f, self.cm.regex_f)),
                        SM( " ENERGY DRIFT PER ATOM \[K\]    =\s+(?P<x_cp2k_md_energy_drift_instantaneous>{})\s+(?P<x_cp2k_md_energy_drift_average>{})".format(self.cm.regex_f, self.cm.regex_f)),
                        SM( " POTENTIAL ENERGY\[hartree\]    =\s+(?P<x_cp2k_md_potential_energy_instantaneous__hartree>{})\s+(?P<x_cp2k_md_potential_energy_average__hartree>{})".format(self.cm.regex_f, self.cm.regex_f)),
                        SM( " KINETIC ENERGY \[hartree\]     =\s+(?P<x_cp2k_md_kinetic_energy_instantaneous__hartree>{})\s+(?P<x_cp2k_md_kinetic_energy_average__hartree>{})".format(self.cm.regex_f, self.cm.regex_f)),
                        SM( " TEMPERATURE \[K\]              =\s+(?P<x_cp2k_md_temperature_instantaneous>{})\s+(?P<x_cp2k_md_temperature_average>{})".format(self.cm.regex_f, self.cm.regex_f)),
                    ],
                ),
            ]
        )

        # Compose root matcher according to the run type. This way the
        # unnecessary regex parsers will not be compiled and searched. Saves
        # computational time.
        self.root_matcher = SM("",
            forwardMatch=True,
            sections=["section_run", "section_sampling_method"],
            subMatchers=[
                SM( "",
                    forwardMatch=True,
                    sections=["section_method"],
                    subMatchers=[
                        self.cm.header(),
                        self.cm.quickstep_header(),
                    ],
                ),
                self.md,
            ]
        )

    #===========================================================================
    # onClose triggers
    def onClose_x_cp2k_section_md_settings(self, backend, gIndex, section):

        # Ensemble
        sampling = section.get_latest_value("x_cp2k_md_ensemble_type")
        if sampling is not None:
            sampling_map = {
                "NVE": "NVE",
                "NVT": "NVT",
                "NPT": "NPT",
            }
            sampling = sampling_map.get(sampling)
            if sampling is not None:
                backend.addValue("ensemble_type", sampling)

        # Sampling type
        backend.addValue("sampling_method", "molecular_dynamics")

        # Print frequencies
        self.output_freq = section.get_latest_value("x_cp2k_md_print_frequency")
        self.energy_freq = section.get_latest_value("x_cp2k_md_energies_print_frequency")
        self.coord_freq = section.get_latest_value("x_cp2k_md_coordinates_print_frequency")
        self.velo_freq = section.get_latest_value("x_cp2k_md_velocities_print_frequency")

        # Step number
        self.n_steps = section.get_latest_value("x_cp2k_md_number_of_time_steps")

        # Files
        coord_filename = section.get_latest_value("x_cp2k_md_coordinates_filename")
        velocities_filename = section.get_latest_value("x_cp2k_md_velocities_filename")
        energies_filename = section.get_latest_value("x_cp2k_md_energies_filename")
        self.file_service.set_file_id(coord_filename, "coordinates")
        self.file_service.set_file_id(velocities_filename, "velocities")
        energies_filepath = self.file_service.set_file_id(energies_filename, "energies")

        # Setup trajectory iterator
        traj_format = self.cache_service["trajectory_format"]
        traj_file = self.file_service.get_file_by_id("coordinates")
        if traj_format is not None and traj_file is not None:

            # Use special parsing for CP2K pdb files because they don't follow the proper syntax
            if traj_format == "PDB":
                self.traj_iterator = cp2kparser.generic.csvparsing.iread(traj_file, columns=[3, 4, 5], start="CRYST", end="END")
            else:
                try:
                    self.traj_iterator = cp2kparser.generic.configurationreading.iread(traj_file)
                except ValueError:
                    pass

        # Setup energy file iterator
        if energies_filepath is not None:
            self.energy_iterator = cp2kparser.generic.csvparsing.iread(energies_filepath, columns=[0, 1, 2, 3, 4, 5, 6], comments="#")

    def onClose_x_cp2k_section_md(self, backend, gIndex, section):

        # Determine the highest print frequency and use that as the number of
        # single configuration calculations
        freqs = {
            "output": [self.output_freq, True],
            "coordinates": [self.coord_freq, True],
            "velocities": [self.velo_freq, True],
            "energies": [self.energy_freq, True],
        }

        # See if the files actually exist
        traj_file = self.file_service.get_file_by_id("coordinates")
        if traj_file is None:
            freqs["coordinates"][1] = False
        velocities_file = self.file_service.get_file_by_id("velocities")
        if velocities_file is None:
            freqs["velocities"][1] = False
        energies_file = self.file_service.get_file_by_id("energies")
        if energies_file is None:
            freqs["energies"][1] = False

        # Determine the highest available frequency
        max_freq = 0
        for freq in freqs.itervalues():
            if freq[0] is not None and freq[1] is not None:
                if freq[0] > max_freq:
                    max_freq = freq[1]
            else:
                freq[1] = False

        # Trajectory print settings
        add_last_traj = False
        add_last_traj_setting = self.cache_service["traj_add_last"]
        if add_last_traj_setting == "NUMERIC" or add_last_traj_setting == "SYMBOLIC":
            add_last_traj = True

        last_step = self.n_steps - 1
        md_steps = section["x_cp2k_section_md_step"]

        frame_sequence_potential_energy = []
        frame_sequence_temperature = []
        frame_sequence_time = []
        frame_sequence_kinetic_energy = []
        frame_sequence_conserved_quantity = []

        i_md_step = 0
        for i_step in range(self.n_steps + 1):

            sectionGID = backend.openSection("section_single_configuration_calculation")
            systemGID = backend.openSection("section_system")

            # Trajectory
            if self.traj_iterator is not None:
                if (i_step + 1) % freqs["coordinates"][0] == 0 or (i_step == last_step and add_last_traj):
                    try:
                        pos = next(self.traj_iterator)
                    except StopIteration:
                        logger.error("Could not get the next geometries from an external file. It seems that the number of optimization steps in the CP2K outpufile doesn't match the number of steps found in the external trajectory file.")
                    else:
                        backend.addArrayValues("atom_positions", pos, unit="angstrom")

            # Energy file
            if self.energy_iterator is not None:
                if (i_step + 1) % freqs["energies"][0] == 0:
                    line = self.energy_iterator.next()

                    time = line[1]
                    kinetic_energy = line[2]
                    temperature = line[3]
                    potential_energy = line[4]
                    conserved_quantity = line[5]
                    wall_time = line[6]

                    frame_sequence_time.append(time)
                    frame_sequence_kinetic_energy.append(kinetic_energy)
                    frame_sequence_temperature.append(temperature)
                    frame_sequence_potential_energy.append(potential_energy)
                    frame_sequence_conserved_quantity.append(conserved_quantity)

                    backend.addValue("energy_total", conserved_quantity)
                    backend.addValue("time_calculation", wall_time)

            # Output file
            if md_steps:
                if (i_step + 1) % freqs["output"][0] == 0:
                    md_step = md_steps[i_md_step]
                    quickstep = md_step.get_latest_value("x_cp2k_section_quickstep_calculation")
                    if quickstep is not None:
                        quickstep.add_latest_value("x_cp2k_atom_forces", "atom_forces")
                        quickstep.add_latest_value("x_cp2k_stress_tensor", "stress_tensor")
                        scfGID = backend.openSection("section_scf_iteration")
                        quickstep.add_latest_value(["x_cp2k_section_scf_iteration", "x_cp2k_energy_total_scf_iteration"], "energy_total_scf_iteration")
                        quickstep.add_latest_value(["x_cp2k_section_scf_iteration", "x_cp2k_energy_change_scf_iteration"], "energy_change_scf_iteration")
                        quickstep.add_latest_value(["x_cp2k_section_scf_iteration", "x_cp2k_energy_XC_scf_iteration"], "energy_XC_scf_iteration")
                        backend.closeSection("section_scf_iteration", scfGID)
                    i_md_step += 1

            backend.closeSection("section_system", systemGID)
            backend.closeSection("section_single_configuration_calculation", sectionGID)

        # Add the summaries to frame sequence
        backend.addArrayValues("frame_sequence_potential_energy", np.array(frame_sequence_potential_energy), unit="hartree")
        backend.addArrayValues("frame_sequence_kinetic_energy", np.array(frame_sequence_kinetic_energy), unit="hartree")
        backend.addArrayValues("frame_sequence_conserved_quantity", np.array(frame_sequence_conserved_quantity), unit="hartree")
        backend.addArrayValues("frame_sequence_temperature", np.array(frame_sequence_temperature))
        backend.addArrayValues("frame_sequence_time", np.array(frame_sequence_time), unit="fs")