from aiida import orm, engine
from aiida.common.exceptions import NotExistent
from aiida.plugins import DataFactory, CalculationFactory


UpfData = DataFactory('upf')
pseudos = {}
absname_pseudo = '/home/amitchell/Dropbox/Professional/Rocstar/OPTImat/pseudo'
pseudo, created = UpfData.get_or_create(absname_pseudo + '/Li.pbe-s-kjpaw_psl.1.0.0.UPF',use_first=False)
pseudos[pseudo.element] = pseudo

alat = 1.5 # angstrom
cell = [[alat, 0., 0.,],
        [0., alat, 0.,],
        [0., 0., alat,],
       ]

StructureData = DataFactory('structure')
s = StructureData(cell=cell)
s.append_atom(position=(0.,0.,0.),symbols='Li')

Dict = DataFactory('dict')
QE_parameters = Dict(dict={
	'SYSTEM': {
		'noinv': False,
		'nosym': False,
		'degauss': 0.00734987,
		'ecutrho': 120,
		'ecutwfc': '{ecutwfc}',
		'noncolin': False,
		'smearing': 'gaussian',
		'vdw_corr': 'none',
		'occupations': 'smearing'
		},
	'CONTROL': {
		'tefield': False,
		'dipfield': False,
		'verbosity': 'high',
		'calculation': 'scf',
		'etot_conv_thr': 1e-05,
		'forc_conv_thr': 0.0001
		},
	'ELECTRONS': {
		'conv_thr': 1e-06,
		'mixing_beta': 0.7,
		'mixing_mode': 'plain',
		'startingwfc': 'atomic',
		'diagonalization': 'david',
		'electron_maxstep': 500,
		'scf_must_converge': False
		}
})

KpointsData = DataFactory('array.kpoints')
kpoints = KpointsData()
kpoints.set_kpoints_mesh([1,1,1])

PwCalculation = CalculationFactory('quantumespresso.pw')
builder = PwCalculation.get_builder()
builder.code = orm.nodes.data.code.Code.get_from_string('pw@laptop')
builder.pseudos = pseudos
builder.structure = s
builder.parameters = QE_parameters
builder.kpoints = kpoints
builder.metadata.dry_run = True
builder.metadata.store_provenance = True
builder.metadata.options.input_filename = 'template.in'
builder.metadata.options.submit_script_filename = 'driver.sh'
result, calc = engine.run_get_node(builder)
abspath = calc._raw_input_folder.abspath 

SingleFileData = DataFactory('singlefile')
driver = SingleFileData(abspath + '/driver.sh')
print(abspath)
parameters = {
	'environment':{
		'keywords':["tabular_data"],
		'tabular_data_file':"List_param_study.dat",
	},
	'method':{
		'id_method': "method1",
		'keywords':["list_parameter_study"],
		'list_of_points':[30, 50],

	},
	'model':{
		'keywords':["single"],
		'id_model': "model1",
		'interface_pointer': "interface1",
		'variables_pointer': "variables1",
		'responses_pointer': "responses1",
	},
	'variables':{
		'keywords':[],
		'id_variables': "variables1",
		'continuous_design':1,
		'descriptors': "ecutwfc",
	},
	'interface':{
		'keywords':["fork", "file_tag", "file_save", "directory_save", "dprepro", "work_directory", "directory_tag", "deactivate", "active_set_vector"],
		'id_interface': "interface1",
		'analysis_driver': "/bin/bash driver.sh",
		'parameters_file': "params.out",
		'results_file': "results.out",
		'copy_files': [f"{absname_pseudo}",f"{abspath + '/template.in'}"],
		'named': "workdir"
	},
	'responses':{
		'keywords':["no_gradients", "no_hessians"],
		'id_responses': "responses1",
		'response_functions':1,
	},
}

# Setting up inputs
computer = orm.load_computer('laptop')
try:
    code = load_code('dakota@laptop')
except NotExistent:
    # Setting up code via python API (or use "verdi code setup")
    code = orm.Code(label='laptop', remote_computer_exec=[computer, '/bin/bash'], input_plugin_name='dakota.study')
builder = code.get_builder()
builder.parameters = Dict(dict=parameters)
builder.driver = driver
builder.metadata.options.driver_filename = 'driver.sh'
builder.metadata.options.withmpi = False
builder.metadata.options.resources = {
    'num_machines': 1,
    'num_mpiprocs_per_machine': 1,
}

# Running the calculation & parsing results
#output_dict, node = engine.run_get_node(builder)
result, calc = engine.run_get_node(builder)
abspath = calc._raw_input_folder.abspath 
print(abspath)
print("Completed.")