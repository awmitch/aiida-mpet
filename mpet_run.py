

from aiida import orm, engine
from aiida.common.exceptions import NotExistent
from aiida.plugins import DataFactory, CalculationFactory

parameters = {
	'Sim Params':{
		'profileType': "CC",
		'Crate': 1,
		'Vmax': 3.6,
		'Vmin': 2.0,
		'Vset': 0.12,
		'power': 1,
		'segments': "[(0.3,0.4),(-0.5,0.1)]",
		'prevDir': False,
		'tend': 1.2e3,
		'tsteps': 200,
		'relTol': 1e-6,
		'absTol': 1e-6,
		'T': 298,
		'randomSeed': False,
		'seed': 0,
		'dataReporter': "hdf5",
		'Rser': 0.,
		'Nvol_c': 10,
		'Nvol_s': 5,
		'Nvol_a': 10,
		'Npart_c': 2,
		'Npart_a': 2,
	},
	'Electrodes':{
		'cathode': "aiida_c.in",
		'anode': "aiida_a.in",
		'k0_foil': 1e0,
		'Rfilm_foil': 0e-0,

	},
	'Particles':{
		'mean_c': 100e-9,
		'stddev_c': 1e-9,
		'mean_a': 100e-9,
		'stddev_a': 1e-9,
		'specified_psd_c': False,
		'specified_psd_a': False,
		'cs0_c': 0.01,
		'cs0_a': 0.99,
	},
	'Conductivity':{
		'simBulkCond_c': False,
		'simBulkCond_a': False,
		'sigma_s_c': 1e-1,
		'sigma_s_a': 1e-1,
		'simPartCond_c': False,
		'simPartCond_a': False,
		'G_mean_c': 1e-14,
		'G_stddev_c': 0,
		'G_mean_a': 1e-14,
		'G_stddev_a': 0,
	},
	'Geometry':{
		'L_c': 50e-6,
		'L_a': 50e-6,
		'L_s': 25e-6,
		'P_L_c': 0.69,
		'P_L_a': 0.69,
		'poros_c': 0.4,
		'poros_a': 0.4,
		'poros_s': 1.0,
		'BruggExp_c': -0.5,
		'BruggExp_a': -0.5,
		'BruggExp_s': -0.5,
	},
	'Electrolyte':{
		'c0': 1000,
		'zp': 1,
		'zm': -1,
		'nup': 1,
		'num': 1,
		'elyteModelType': "SM",
		'SMset': "valoen_bernardi",
		'n': 1,
		'sp': -1,
		'Dp': 2.2e-10,
		'Dm': 2.94e-10,
	},
}

cathode_parameters = {
	'Particles': {
		'type': "ACR",
		'discretization': 1e-9,
		'shape': "C3",
		'thickness': 20e-9,
	},
	'Material': {
		'muRfunc': "LiFePO4",
		'logPad': False,
		'noise': False,
		'noise_prefac': 1e-6,
		'numnoise': 200,
		'Omega_a': 1.8560e-20,
		'kappa': 5.0148e-10,
		'B': 0.1916e9,
		'rho_s': 1.3793e28,
		'D': 5.3e-19,
		'Dfunc': "lattice",
		'dgammadc': 0e-30,
		'cwet': 0.98,
	},
	'Reactions': {
		'rxnType': "BV",
		'k0': 1.6e-1,
		'E_A': 13000,
		'alpha': 0.5,
		# Fraggedakis et al. 2020, lambda: 8.3kBT
		'lambda': 3.4113e-20,
		'Rfilm': 0e-0,
	},
}
anode_parameters = {
	'Particles': {
		'type': "CHR",
		'discretization': 2.5e-8,
		'shape': "cylinder",
		'thickness': 20e-9,
	},
	'Material': {
		'muRfunc': "LiC6_1param",
		'logPad': False,
		'noise': False,
		'noise_prefac': 1e-6,
		'numnoise': 200,
		'Omega_a': 1.3992e-20,
		'Omega_b': 5.761532e-21,
		'kappa': 4.0e-7,
		'B': 0.0,
		'rho_s': 1.7e28,
		'D': 1.25e-12,
		'Dfunc': "lattice",
		'dgammadc': 0e-30,
		'cwet': 0.98,
	},
	'Reactions': {
		'rxnType': "BV",
		'k0': 3.0e+1,
		'E_A': 50000,
		'alpha': 0.5,
		# Fraggedakis et al. 2020, lambda: 8.3kBT
		'lambda': 2.055e-20,
		'Rfilm': 0e-0,
	},
}


# Setting up inputs
computer = orm.load_computer('workstation')
try:
    code = load_code('mpet@workstation')
except NotExistent:
    # Setting up code via python API (or use "verdi code setup")
    code = orm.Code(label='workstation', remote_computer_exec=[computer, '/bin/bash'], input_plugin_name='mpet.mpetrun')
builder = code.get_builder()
builder.parameters = Dict(dict=parameters)
builder.cathode_parameters = Dict(dict=cathode_parameters)
builder.anode_parameters = Dict(dict=anode_parameters)
builder.metadata.options.withmpi = True
builder.metadata.options.resources = {
    'num_machines': 1,
    'num_mpiprocs_per_machine': 1,
}
# builder.settings = Dict(dict={
# 	'CMDLINE':'python3.7'
# })

# Running the calculation & parsing results
#output_dict, node = engine.run_get_node(builder)
result, calc = engine.run_get_node(builder)
abspath = calc._raw_input_folder.abspath 
print(abspath)
print("Completed.")