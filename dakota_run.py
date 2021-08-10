from aiida import orm, engine
from aiida.common.exceptions import NotExistent

parameters = {
	'environment':{
		'keywords':["tabular_data"],
		'tabular_data_file':"List_param_study.dat",
	},
	'method':{
		'id_method': "method1",
		'keywords':["list_parameter_study"],
		'list_of_points':[0.00734987, 0.008],

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
		'descriptors': "degauss",
	},
	'interface':{
		'keywords':["fork", "file_tag", "file_save"],
		'id_interface': "interface1",
		'analysis_driver': "driver.py",
		'parameters_file': "params.out",
		'results_file': "results.out",
	},
	'responses':{
		'keywords':["no_gradients", "no_hessians"],
		'id_responses': "responses1",
		'response_functions':1,
	},
}

								
	  
	parameters_file = 'params.in'
	results_file = 'results.out'
	file_tag
	file_save


# Setting up inputs
computer = orm.load_computer('laptop')
try:
    code = load_code('dakota@laptop')
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
calculation = engine.run(builder)
print("Completed.")