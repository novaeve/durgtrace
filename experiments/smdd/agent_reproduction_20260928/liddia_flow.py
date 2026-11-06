"""Interface validation and repair context; no molecule selection policy."""
import json
import re


class CodeExecutionError(ValueError):
    pass


def validate_inputs(name, inputs, desc, stream, pocket_id):
    if name == 'GENERATE':
        if inputs != [pocket_id]:
            raise ValueError('GENERATE requires the available pocket ID')
        return
    if name == 'CODE':
        if not inputs or any(type(k) is not str for k in inputs):
            raise ValueError('CODE requires a nonempty list of molecule-set IDs')
        missing = sorted(set(re.findall(r'\bMOL\d+\b', desc))-set(inputs))
        if missing:
            raise ValueError('CODE Desc references '+str(missing)+' but they are not in Input. Include every referenced set in Input, or use existing columns without referencing another set.')
        ids = inputs
    else:
        if len(inputs) != 2 or type(inputs[0]) is not str:
            raise ValueError(name+' requires [molecule_set_ID, objective_or_row_index]')
        ids = inputs[:1]
        if name == 'OPTIMIZE' and type(inputs[1]) is not str:
            raise ValueError('OPTIMIZE requires a string objective')
        if name in ('ADMET', 'BOLTZ', 'SUBMIT') and type(inputs[1]) is not int:
            raise ValueError('Row index must be an integer')
    for key in ids:
        if key not in stream or stream[key]['type'] != 'MOL':
            raise ValueError('Unknown molecule-set ID: '+str(key))
    if name in ('ADMET', 'BOLTZ', 'SUBMIT') and not 0 <= inputs[1] < len(stream[inputs[0]]['data']):
        raise ValueError('Row index out of range')


def code_prompt(template, data, desc, previous_source=None, previous_error=None):
    columns = sorted(set(c for df in data.values() for c in df.columns))
    template = re.sub(r'The dataframe has these columns:.*',
                      'The dataframe has these columns: '+str(columns)+'.', template)
    template = template.replace('def _function(Dict[str, pd.DataFrame])',
                                'def _function(data: dict[str, pd.DataFrame])')
    prompt = template.format(input_desc=desc)
    # The upstream example incorrectly ends its fence with ```python.
    if prompt.count('```python') > 1:
        pos = prompt.rfind('```python')
        prompt = prompt[:pos]+'```'+prompt[pos+9:]
    schema = {key: {'rows': len(df), 'columns': list(df.columns)} for key, df in data.items()}
    prompt += '\nRuntime contract:\n'+json.dumps(schema)+'\n'
    prompt += ('Only these dictionary keys exist; access frames as data[set_ID]. Return selected existing molecule rows as a DataFrame with SMILES, not a list of indices. '
               'An empty result is valid. Do not invent reference molecules, property values, or substitute proxy scores for missing measurements. '
               'SAScore and Similarity are already provided; Similarity uses Morgan radius 2, 2048 bits against the task reference. '
               'Use those columns when possible. Allowed import roots: pandas, numpy, rdkit, math, typing, collections, re. '
               'For SA recomputation use from rdkit.Contrib.SA_Score import sascorer. Do not import os, sys or standalone sascorer or modify sys.path. '
               'There is no network, prediction service, or model checkpoint available.\n')
    if previous_error:
        prompt += '\nPrevious attempt failed. Fix this concrete error while keeping the requested operation:\n'+previous_error[-2000:]
        prompt += '\nPrevious source:\n```python\n'+(previous_source or '')+'\n```\n'
    return prompt


def parse_goal(response):
    answers = re.findall(r'^\s*Answer:\s*(YES|NO)\s*$', response, re.M)
    reasons = re.findall(r'^\s*Reason:[ \t]*(.+)$', response, re.M)
    if not answers or not reasons:
        raise ValueError('Goal response requires Reason and Answer: YES or NO')
    return answers[-1], reasons[-1]
