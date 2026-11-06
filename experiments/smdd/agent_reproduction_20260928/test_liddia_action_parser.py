import json
import unittest
from pathlib import Path
from liddia_action_parser import parse_action, ActionParseError

ALLOWED = ['GENERATE000', 'OPTIMIZE001', 'CODE002', 'ADMET003', 'BOLTZ004', 'SUBMIT005']


class ParserTests(unittest.TestCase):
    def test_actual_failed_response_and_previous_decisions(self):
        calls = json.loads((Path(__file__).parent/'type4_pilot/llm_calls.json').read_text(encoding='utf-8'))
        for call in calls:
            if call['label'] == 'decision':
                with self.subTest(call=calls.index(call)):
                    parse_action(call['output'], ALLOWED)
        action, inputs, desc = parse_action(calls[-1]['output'], ALLOWED)
        self.assertEqual((action, inputs), ('CODE002', ['MOL010']))
        self.assertTrue(desc.startswith('Filter MOL010 rows'))

    def test_final_block_keeps_its_own_description(self):
        response = "Action: CODE002\nInput: ['MOL007']\nDesc: old\n\nFinal answer:\n```\nAction: CODE002\nInput: ['MOL010']\nDesc: new\nsecond line\n```"
        self.assertEqual(parse_action(response, ALLOWED), ('CODE002', ['MOL010'], 'new\nsecond line'))

    def test_reject_malformed_without_falling_back(self):
        for ending in ["Action: BOLTZ004\nInput: bad", "Action: FAKE999\nInput: []", "Action: CODE002\nInput: ['MOL010']", "Action: BOLTZ004\nInput: ['MOL010'], Desc: inline", "Action: BOLTZ004\nInput: __import__('os').getcwd()", "Action: BOLTZ004\nInput: {'id': 1}"]:
            with self.subTest(ending=ending), self.assertRaises(ActionParseError):
                parse_action("Action: BOLTZ004\nInput: ['MOL007', 0]\n\n"+ending, ALLOWED)

    def test_boltz_row_index(self):
        self.assertEqual(parse_action("Action: BOLTZ004\nInput: ['MOL010', 0]", ALLOWED), ('BOLTZ004', ['MOL010', 0], ''))

    def test_blank_lines_from_parserfix_run(self):
        response="Action: OPTIMIZE001  \n\nInput: ['MOL007', 'clearance']  \n\nDesc: Optimize the input.\n"
        self.assertEqual(parse_action(response, ALLOWED), ('OPTIMIZE001', ['MOL007', 'clearance'], 'Optimize the input.'))


if __name__ == '__main__':
    unittest.main()
