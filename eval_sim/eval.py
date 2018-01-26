import argparse
import ast
import gzip
import itertools
import re
from collections import Counter
from operator import attrgetter, sub
from typing import List

import sys

import numpy as np
import pickle

from evaluation_tools.Evaluator import evaluate_file, count_fails, init, Result, Faulttype

noc_rg = init()

parser = argparse.ArgumentParser(description='Evaluation the result of a Reliability-analysis simulation.')
parser.add_argument('infile', type=str, help='The inputfile to read, either a `.results` file or a `results.gz`.')
parser.add_argument('--verbose', action='store_true',
                    help='Prints progress and additional information.')
parser.add_argument('--output-type', nargs='?', choices=['default', 'single-line', 'key-value-pairs'],
                    default='default', help='The way the output should be printed.')
parser.add_argument('--write-results', nargs='?', type=argparse.FileType('wb'), default=None,
                    help="Stores the intermediate result objects to the given gzip file.")
parser.add_argument('--read-results', nargs='?', type=argparse.FileType('rb'), default=None,
                    help="Loads intermediate result objects from the given gzip file instead of evaluating `infile`.")
parser.add_argument('--routerinfo', type=argparse.FileType('r'), default=None,
                    help="The file with the routers description..")

args = parser.parse_args()

filename = args.infile
verbose = args.verbose

if verbose:
    print("evaluating %s" % filename)

refdata = {}
if args.routerinfo:
    for line in args.routerinfo.readlines():
        if line.strip():
            l, r = line.split('=', 1)
            refdata[l] = ast.literal_eval(r)
modules:List[str]=refdata["modules"]
refdata['nrfaultlocs'] = sum(refdata['locspermodule'].values())
if 'none' in modules:
    modules.remove('none')
tldmodules=modules

results: List[Result] = None
errornous, results = [], []
if args.read_results:
    results = pickle.load(gzip.open(args.read_results, 'rb'))
else:
    errornous, results = evaluate_file(noc_rg, filename, print_verbose=verbose)
if args.write_results:
    pickle.dump(results, gzip.open(args.write_results, 'wb'))
faillist = count_fails(results)
numresults = float(len(results))
if verbose:
    res: List[Result] = [r for r in results if not r.vcd_of_module_equal]
    print("%d without module data" % len([r for r in res if r.errornous]))

for m in modules:
    if m not in results[0].vcd_of_module_equal:
        print("vcd_of_module is strange: %s (modules=%s)"%(str(results[0].vcd_of_module_equal.keys()),str(modules)),file=sys.stderr)
        if m == "allocator":
            print("Fixing: vcd_of_module_equal, switching all arbiters to the allocator",file=sys.stderr)
            for r in results:
                r.vcd_of_module_equal["allocator"] = r.vcd_of_module_equal["arbiter"]
# how often the output of each module was changed because of a fault.
module_changed_counts = {n: sum(1 for r in results if r.vcd_of_module_equal and not r.vcd_of_module_equal[n])
                         for n in modules}
# how often a fault was injected into a module
param_module_counts = {n: sum(1 for r in results if r.getFaultModuleFromParam() and r.getFaultModuleFromParam().startswith(n)) for n in modules}
param_module_changed_counts = 'invalid'
param_module_changed_and_invalid_counts = 'invalid'
param_module_changed_and_invalid_ratios = 'invalid'
param_module_changed_ratios = 'invalid'
module_output_changed_when_system_failed_counts = 'invalid'
param_module_changed_and_invalid_total_ratios = 'invalid'
param_module_changed_total_ratios = 'invalid'
experiments_per_module = 'invalid'
violations_per_module = 'invalid'
uncorrect_module_ratios = 'invalid'
correction_multipliers = 'invalid'
faulttype_caused_by_module = 'invalid'
faulttype_caused_by_module_when_invalid = 'invalid'
faulttype_caused_by_module_when_module_output_changed_and_invalid = 'invalid'
faulttype_and_module_output_changed = 'invalid'
faulttype_counts_corrected = 'invalid'
faulttype_ratios = 'invalid'



module_output_changed_when_system_failed_ratio = 'invalid'
invalids = [r for r in results if not r.is_valid()]
m_all = {m: list(filter(lambda r: r.getFaultModuleFromParam() == m, results)) for m in modules}
# accumulate the fifo with fifod and fifoc
m_all_fixed_fifo = {m: list(filter(lambda r: r.getFaultModuleFromParam().startswith(m) if r.getFaultModuleFromParam() else False, results)) for m in modules}
m_invalid = {m: list(filter(lambda r: not r.is_valid(), m_all[m])) for m in modules}
num_runs = len(results)
m_invalid_fixed_fifo = {m: list(filter(lambda r: not r.is_valid(), m_all_fixed_fifo[m])) for m in modules}
ratio_violations_per_module = {m: len(m_invalid[m]) / (len(m_all[m]) + 1) for m in modules}
violations_per_module = {m: len(m_invalid[m]) for m in modules}

module_size_ratio = {m: refdata['locspermodule'][m] / refdata['nrfaultlocs'] for m in modules}


experiments_per_module = {k: len(v) for k, v in m_all_fixed_fifo.items()}
for k, v in experiments_per_module.items():
    if v == 0:
        print("Error: experiments_per_module[%s] is 0"%k,file=sys.stderr)
        exit()
violations_per_module = {k: len(v) for k, v in m_invalid_fixed_fifo.items()}

uncorrect_module_ratios = {k: (v / float(num_runs)) for k, v in experiments_per_module.items()}
for k, v in uncorrect_module_ratios.items():
    if v == 0:
        print("Error: uncorrect_module_ratios[%s] is 0"%k,file=sys.stderr)
correction_multipliers = {k: module_size_ratio[k] /v for k, v in uncorrect_module_ratios.items()}
corrected_ratio = sum([violations_per_module[m] * correction_multipliers[m] for m in tldmodules])/num_runs

param_module_failed_corrected_counts  = {n: sum(1 for r in m_invalid_fixed_fifo[n])* correction_multipliers[n] for n in modules}
        
param_module_failed_corrected_ratio  = {k: v/num_runs for k,v in param_module_failed_corrected_counts.items()}

# do this only when there is actually module data!
if len(results[0].vcd_of_module_equal) >= 4:

    # how often the output of the params module was changed
    param_module_changed_counts = {
        n: sum(1 for r in m_all_fixed_fifo[n] if  not r.vcd_of_module_equal[n]) for n
        in
        modules}
    param_module_changed_and_invalid_counts = {n: sum(1 for r in m_invalid_fixed_fifo[n] if
                                                            not
                                                           r.vcd_of_module_equal[n] ) for n in
                                               modules}
    param_module_changed_ratios = {n: param_module_changed_counts[n] / float(param_module_counts[n])
                                   for
                                   n in modules}
    param_module_changed_and_invalid_ratios = {n: param_module_changed_and_invalid_counts[n] / (
        float(param_module_changed_counts[n]) if float(param_module_changed_counts[n]) > 0 else -1) for n in
                                               modules}
    module_output_changed_when_system_failed_counts = {
        n: sum(
            1 for r in invalids if r.vcd_of_module_equal and not r.vcd_of_module_equal[n])
        for n in modules}

    param_module_changed_and_invalid_total_ratios = dict(
        [(k, v * correction_multipliers[k] / float(num_runs)) for k, v in
         param_module_changed_and_invalid_counts.items()])
    param_module_changed_total_ratios = dict(
        [(k, v * correction_multipliers[k] / float(num_runs)) for k, v in param_module_changed_counts.items()])

    module_output_changed_when_system_failed_ratio = dict(
        [(k, v * correction_multipliers[k] / float(num_runs)) for k, v in
         module_output_changed_when_system_failed_counts.items()])

    faulttype_caused_by_module = {f.name:
                                      {m: sum(
                                          1 for r in m_all_fixed_fifo[m] if r.hasError(f)) for
                                       m in modules} for f in Faulttype}
    faulttype_caused_by_module_corrected = {f.name:
        {m: faulttype_caused_by_module[f.name][m] * correction_multipliers[m] for
            m in modules} for f in Faulttype}

    faulttype_caused_by_module_when_invalid = {
        f.name: {
        m: sum(1 for r in m_invalid_fixed_fifo[m] if r.hasError(f)) for m
        in modules}
        for f in Faulttype}
    faulttype_caused_by_module_when_module_output_changed_and_invalid = {
        f.name: {m: sum(
            1 for r in m_invalid_fixed_fifo[m] if r.hasError(f) and not r.vcd_of_module_equal[m]) for m
                 in
                 modules} for
        f in Faulttype}
    faulttype_and_module_output_changed = {
        f.name: {m: sum(1 for r in invalids if r.hasError(f) and not r.vcd_of_module_equal[m]) for m in
                 modules}
        for
        f in Faulttype}
    faulttype_counts_corrected = {
    f.name: sum(faulttype_caused_by_module[f.name][m] * correction_multipliers[m] for m in tldmodules) for
    f in Faulttype}
    faulttype_counts = {
        f.name: sum(1 for i in invalids if i.hasError(f))
    for
        f in Faulttype}
    faulttype_ratios_given_invalid = {f.name: sum(1 for i in invalids if i.hasError(f)) / len(invalids) for f in Faulttype}
    faulttype_ratios_total = {f.name: sum(1 for i in invalids if i.hasError(f)) / num_runs for f in Faulttype}
    faulttype_correlation = {f2.name: {f1.name: sum(1 for i in invalids if i.hasError(f1) and i.hasError(f2)) / faulttype_counts[f1.name] for f1 in Faulttype}for f2 in Faulttype}
    faulttype_caused_by_module_ratio_corrected = {f.name:
        {m: (faulttype_caused_by_module[f.name][m]*correction_multipliers[m])/faulttype_counts_corrected[f.name] for
            m in modules} for f in Faulttype}

all_result = (
    attrgetter('name', 'errornous', 'unexpected_len_sent', 'unexpected_len_recv', 'len_sent', 'len_recv',
               'sents_invalid',

               'recv_invalid', 'params', 'connection_counter_invalid', 'misrouted_recv', 'misrouted_sent')(obj) for obj
    in results)
names, errors, uls, ulr, ls, lr, si, ri, params, ff, mr, ms = itertools.zip_longest(*all_result)

acc_result = {
    'num_runs': len(results),
    'num_violations': len(faillist),
    'ratio_violations': len(faillist) / numresults,
    'corrected_ratio': corrected_ratio,
    'module_sizes_relative_to_router': module_size_ratio,
    'sim_errors': len(errornous),
    'experiments_per_module': experiments_per_module,
    'violations_per_module': violations_per_module,
    'ratio_violations_per_module': ratio_violations_per_module,
    'module_changed_counts': module_changed_counts,
    'param_module_counts': param_module_counts,
    'param_module_failed_corrected_counts':param_module_failed_corrected_counts,
    'param_module_failed_corrected_ratio':param_module_failed_corrected_ratio,
    'param_module_changed_counts': param_module_changed_counts,
    'param_module_changed_ratios': param_module_changed_ratios,
    'param_module_changed_and_invalid_counts': param_module_changed_and_invalid_counts,
    'param_module_changed_and_invalid_ratios': param_module_changed_and_invalid_ratios,
    'module_output_changed_when_system_failed_counts': module_output_changed_when_system_failed_counts,
    'ref_locs_per_module': refdata['locspermodule'],
    'param_module_changed_and_invalid_total_ratios': param_module_changed_and_invalid_total_ratios,
    'param_module_changed_total_ratios': param_module_changed_total_ratios,
    'uncorrect_module_ratios': uncorrect_module_ratios,
    'correction_multipliers': correction_multipliers,
    'module_output_changed_when_system_failed_ratio': module_output_changed_when_system_failed_ratio,
    'faulttype_caused_by_module': faulttype_caused_by_module,
    'faulttype_caused_by_module_corrected' : faulttype_caused_by_module_corrected,
    'faulttype_caused_by_module_ratio_corrected':faulttype_caused_by_module_ratio_corrected,
    'faulttype_caused_by_module_when_invalid': faulttype_caused_by_module_when_invalid,
    'faulttype_caused_by_module_when_module_output_changed_and_invalid': faulttype_caused_by_module_when_module_output_changed_and_invalid,
    'faulttype_and_module_output_changed': faulttype_and_module_output_changed,
    'faulttype_counts_corrected': faulttype_counts_corrected,
    'faulttype_counts': faulttype_counts,
    'faulttype_ratios_given_invalid': faulttype_ratios_given_invalid,
    'faulttype_ratios_total': faulttype_ratios_total,
    'faulttype_correlation':faulttype_correlation
}

if args.output_type == 'single-line':
    print(' '.join(str(x) for x in [acc_result['num_runs'],
                                    acc_result['num_violations'],
                                    acc_result['percentage_violations'],
                                    acc_result['sim_errors']]))
if args.output_type == 'key-value-pairs':
    for k, v in acc_result.items():
        print('%s : %s' % (str(k), str(v)))

if args.output_type == 'default':
    if verbose:
        print("------------Statistics---------------")
    print('Total Number of runs: %d' % acc_result['num_runs'])
    print("Runs with unexpected behavior: %d Ratio: %f" % (
        acc_result['num_violations'], acc_result['percentage_violations']))
    print('IDs: %s' % ' '.join(sorted([obj.name for obj in results if not obj.is_valid()])))
    print('Total number of simulation errors: %d' % len(errornous))
    print('Total number of runs with an unexpected amount of sent flits: %d' % sum(uls))
    print('Total number of runs with an unexpected amount of recv flits: %d' % sum(ulr))
    print('Runs where the number of sent flits and the number of received flits differs between 2 nodes: %d' % sum(ff))
    print('Maximum number of sent flits: %d' % max(ls))
    print('Average number of sent flits: %f' % (sum(ls) / float(len(ls))))
    print('Minimum number of sent flits: %d' % min(ls))
    print('Maximum number of recv flits: %d' % max(lr))
    print('Average number of recv flits: %f' % (sum(lr) / float(len(lr))))
    print('Minimum number of recv flits: %d' % min(lr))
    print('Average difference between number of sent and received flits: %f' % (sum(map(sub, ls, lr)) / float(len(ls))))
    avg_dif_wdif_list = list(filter(lambda x: x != 0, map(sub, ls, lr)))
    if len(avg_dif_wdif_list) != 0:
        avg_dif_wdif = sum(map(abs, avg_dif_wdif_list)) / float(len(avg_dif_wdif_list))
        print('Average difference between number of sent and received flits (only when different): %f' % avg_dif_wdif)
        print('Average absolute difference between number of sent and received flits (only when different): %f' % (
            sum(map(abs, avg_dif_wdif_list)) / float(len(avg_dif_wdif_list))))
        print('Variance of the difference between number of sent and received flits (only when different): %f' % np.var(
            avg_dif_wdif_list))
    else:
        print("No differences in amount of sent and received packets!")

    print('Average number of wrong injected flits: %d' % (sum(ms) / float(len(ms))))
    print('Average number of wrong routed flits (XY Routing): %d' % (sum(mr) / float(len(mr))))
    print('Maximum number of wrong routed flits (XY Routing): %d' % max(mr))

    print('Average number of flits which failed the verification on the sent side: %d' % (sum(si) / float(len(si))))
    print('Average number of flits which failed the verification on the recv side: %d' % (sum(ri) / float(len(ri))))
    paramlist = [obj.params.split(' ')[:6] + [' '.join(obj.params.split(' ')[6:])] for obj in results if
                 not obj.is_valid()]
    if len(paramlist) == 0:
        print("No faults detected!")
    else:
        breaktimes, breaktimesa, faultvalues, faultlengths, breakname1, breakname2, additionals = itertools.zip_longest(
            *paramlist)
        breaktimes = list(map(int, breaktimes))
        faultvalues = list(map(int, faultvalues))
        print('Average breaktime which lead to a fault: %f' % (sum(breaktimes) / float(len(breaktimes))))
        print('Maximum breaktime which lead to a fault: %f' % (max(breaktimes)))
        print('Average faultvalue: %f' % (sum(faultvalues) / float(len(faultvalues))))
        print('Which pins broke something statistic: ')
        print(Counter(breakname2))
        # Look at difflib, maybe matching blocks, maybe consider buckets
        total = 0
        for pattern in [r'^U', r'^valid_', r'^[\\]*CONTROL_PART/allocator_unit', r'^[\\]*CONTROL_PART/LBDR',
                        r'^[\\]*FIFO_[NESLW]/FIFO_comb', r'^[\\]*FIFO_[NESLW]/FIFO_seq', r'^[\\]*XBAR']:
            tmp = len(list(filter(lambda s: re.match(pattern, s.guessComponent()) is not None, faillist)))
            total += tmp
            print('"%s" broke something: %d' % (pattern, tmp))
        if total < len(breakname2):
            print('Missed %d patterns!' % (len(breakname2) - total))

            # convert to cell name and connected pin list.
            # for obj in faillist:
            #    print(obj.guessComponent(), obj.params)
    if verbose:
        print("------------Statistics---------------")
