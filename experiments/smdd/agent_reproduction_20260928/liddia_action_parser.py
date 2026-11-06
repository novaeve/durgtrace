"""Parse the final line-oriented LIDDIA action without executing model text."""
import ast
import re


class ActionParseError(ValueError):
    pass


def parse_action(response, allowed_actions):
    # Explanatory inline mentions are not commands. Never fall back to an older
    # action if the final declared action is malformed.
    starts = list(re.finditer(r'^\s*Action:[ \t]*', response, re.M))
    if not starts:
        raise ActionParseError('Expected a final Action/Input block')
    block = response[starts[-1].end():].strip()
    if block.endswith('```'):
        block = block[:-3].rstrip()
    match = re.fullmatch(
        r'(?P<action>[A-Z]+\d{3})[ \t]*\n\s*Input:[ \t]*(?P<input>[^\n]+)'
        r'(?:\n\s*Desc:[ \t]*(?P<desc>.*))?\s*', block, re.S)
    if not match:
        raise ActionParseError('Use separate Action: ID, Input: Python list, and optional Desc: lines')
    action = match['action']
    if action not in allowed_actions:
        raise ActionParseError('Unknown action ID: ' + action)
    try:
        inputs = ast.literal_eval(match['input'].strip())
    except (ValueError, SyntaxError, TypeError, RecursionError) as exc:
        raise ActionParseError('Input must be a literal Python list') from exc
    if not isinstance(inputs, list) or not all(type(x) in (str, int) for x in inputs):
        raise ActionParseError('Input must be a list of string IDs and integer row indices')
    desc = (match['desc'] or '').strip()
    if action.startswith('CODE') and not desc:
        raise ActionParseError('CODE requires Desc in the same final action block')
    return action, inputs, desc
