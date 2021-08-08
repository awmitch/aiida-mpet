from aiida import orm, engine
from aiida.common.exceptions import NotExistent

parameters = {
	'ENVIRONMENT':{
		'keywords':[tabular_data],
		'tabular_data_file':'List_param_study.dat',
	},
	'METHOD':{
		'keywords':['list_parameter_study'],
		'list_of_points':[0.00734987, 0.008],

	},
	'MODEL':{
		'keywords':[],
	},
	'VARIABLES':{
		'keywords':[],
		'continuous_design':1
		'descriptors':'degauss'
	},
	'INTERFACE':{
		'keywords':[],
	},
	'RESPONSES':{
		'keywords':[no_gradients, no_hessians],
		'response_functions':1
	},
}


# Setting up inputs
computer = orm.load_computer('localhost')
try:
    code = load_code('dakota@localhost')
except NotExistent:
    # Setting up code via python API (or use "verdi code setup")
    code = orm.Code(label='laptop', remote_computer_exec=[computer, '/bin/bash'], input_plugin_name='dakota.study')

builder = code.get_builder()
builder.parameters = Dict(dict=parameters)
	
builder.metadata.options.withmpi = False
builder.metadata.options.resources = {
    'num_machines': 1,
    'num_mpiprocs_per_machine': 1,
}

# Running the calculation & parsing results
#output_dict, node = engine.run_get_node(builder)
calculation = engine.submit(builder)
print("Completed.")