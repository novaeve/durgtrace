"""Classify the final native segment, including recoverable SoL-Pi aborts."""


def outcome(proc, events, truncations, before, exhausted, answer_known):
    if proc.stalled:
        return 'stalled'
    assistants = [event['message'] for event in events
                  if event.get('type') == 'message_end'
                  and event.get('message', {}).get('role') == 'assistant']
    terminal_error = bool(assistants and assistants[-1].get('stopReason') == 'error')
    if not proc.returncode and not terminal_error and exhausted and answer_known:
        return 'completed'
    if truncations >= 3:
        return 'provider_limit'
    # Pi JSON mode can report an error with exit code zero.
    if truncations > before:
        return 'retry_truncation'
    if proc.returncode or terminal_error:
        return 'error'
    return 'continue_session'


def check_policy():
    from types import SimpleNamespace
    ok = SimpleNamespace(returncode=0, stalled=False)
    failed = SimpleNamespace(returncode=1, stalled=False)
    stalled = SimpleNamespace(returncode=-15, stalled=True)
    def message(stop):
        return {'type': 'message_end', 'message': {'role': 'assistant', 'stopReason': stop}}
    error = [message('error')]
    recovered = error + [{'type': 'compaction_start'}] + [message('stop')]
    assert outcome(ok, error, 1, 0, False, False) == 'retry_truncation'
    assert outcome(failed, error, 1, 0, False, False) == 'retry_truncation'
    assert outcome(ok, error, 2, 1, False, False) == 'retry_truncation'
    assert outcome(ok, error, 3, 2, False, False) == 'provider_limit'
    assert outcome(ok, recovered, 0, 0, True, True) == 'completed'
    assert outcome(ok, error, 0, 0, True, True) == 'error'
    assert outcome(stalled, recovered, 0, 0, False, False) == 'stalled'
    assert outcome(ok, [message('stop')], 0, 0, False, False) == 'continue_session'
    assert outcome(ok, recovered, 0, 0, True, False) == 'continue_session'
    return {'accepted': True, 'cases': 9}


if __name__ == '__main__':
    import json
    print(json.dumps(check_policy()))
