#!/usr/bin/env python3
from aiida.engine import run_get_pk
from aiida import load_profile
from aiida.orm import load_node
import dakota.interfacing as di


# Dakota will execute this script as
#   driver.py params.in results.out
#  The command line arguments will be extracted by dakota.interfacing automatically.


def pack_plugin_parameters(dakota_params, dakota_results):
    """Pack plugin_list input dictionary
    
    """
    for key in dakota_params.items

    continuous_vars = [ dakota_params['degauss'] ]

    active_set_vector = 0
    if dakota_results["obj_fn"].asv.function:
        active_set_vector += 1
    if dakota_results["obj_fn"].asv.gradient:
        active_set_vector += 2
    if dakota_results["obj_fn"].asv.hessian:
        active_set_vector += 4
    
    plugin_input = {
        "cv": continuous_vars,
        "functions": 1,
        "asv": [active_set_vector]
    }    

    return plugin_input


def pack_dakota_results(plugin_output, dakota_results):
    """Insert results from plugin into Dakota results

    Although we need to handle just one response, this function demonstrates iteration
    over response labels (or descriptors) for educational purposes.
    """
    for i, label in enumerate(dakota_results):
        if dakota_results[label].asv.function:
            dakota_results[label].function = plugin_output["fns"][i]
        if dakota_results[label].asv.gradient:
            dakota_results[label].gradient = plugin_output["fnGrads"][i]
        if dakota_results[label].asv.hessian:
            dakota_results[label].hessian = plugin_output["fnHessians"][i]
    
    return dakota_results


def main():

    params, results = di.read_parameters_file()

    plugin_input = pack_plugin_parameters(params, results)

    plugin_output = run_get_pk(Plugin,**plugin_input)
    
    results = pack_dakota_results(plugin_output, results)
    results.write()


if __name__ == '__main__':
    main()
