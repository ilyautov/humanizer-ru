"""Regression cases for numeric preservation and bounded fact verdicts."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/humanizer-ru/scripts'))
from humanizer_metrics.facts import diff_facts, facts_verdict, extract_facts

class NumericFactsTests(unittest.TestCase):
    def test_changed_values(self):
        for a,b in [('Цена 1,5 млн рублей.', 'Цена 15 млн рублей.'),
                    ('Формат А4.', 'Формат А3.'),
                    ('Температура −5 градусов.', 'Температура 5 градусов.'),
                    ('Рост 5 процентных пунктов.', 'Рост 5 процентов.'),
                    ('Срок 1/2 года.', 'Срок 12 года.'),
                    ('Температура -5 градусов.', 'Температура 5 градусов.'),
                    ('Комиссия 5 процентов.', 'Комиссия 5 рублей.'),
                    ('Бюджет 5 млн рублей.', 'Бюджет 5 тыс рублей.')]:
            with self.subTest(a=a, b=b):
                d = diff_facts(a,b)
                self.assertTrue(d.added or d.lost)
    def test_equivalent_notation(self):
        for a,b in [('Цена 1,5 млн рублей.', 'Цена 1.5 млн рублей.'),
                    ('Цена 1 500 рублей.', 'Цена 1500 руб.'),
                    ('Комиссия 5 процентов.', 'Комиссия 5%.'),
                    ('Цена 1\u202f500 рублей.', 'Цена 1500 ₽.')]:
            with self.subTest(a=a,b=b):
                d = diff_facts(a,b)
                self.assertFalse(d.added or d.lost, d)
    def test_no_semantic_guarantee(self):
        d = diff_facts('Выручка 10, прибыль 2.', 'Выручка 2, прибыль 10.')
        self.assertFalse(d.as_dict()['semantic_verified'])
        self.assertIn('смысл', facts_verdict(d).lower())
        self.assertNotIn('факт-замок цел', facts_verdict(d))
    def test_loss_not_claimed_intact(self):
        d=diff_facts('Срок 15 дней.', 'Срок неизвестен.')
        self.assertEqual(d.as_dict()['status'], 'review_required')
        self.assertNotIn('на месте', facts_verdict(d))
    def test_python_browser_numeric_parity(self):
        from humanizer_metrics.facts import numeric_facts
        texts=['1,5 млн рублей', '15 млн рублей', '5 процентов', '5 процентных пунктов',
               'Формат А4.', 'Температура −5 градусов.', '1 500 руб.', '1\u202f500 ₽.',
               '+005', '-0', '10.05.2026', '5000-8000', '10000000000000000000000']
        source="const fs=require('fs'),vm=require('vm');vm.runInThisContext(fs.readFileSync('docs/scan-rules.js','utf8'));vm.runInThisContext(fs.readFileSync('docs/scan.js','utf8'));const texts="+json.dumps(texts)+";process.stdout.write(JSON.stringify(texts.map(t=>Object.fromEntries(humanizerNumericFacts(t)))));"
        p=subprocess.run(['node','-e',source],cwd=ROOT,text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(p.stdout),[numeric_facts(t) for t in texts])

    def test_empty_before_json(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'before';p.write_text('')
            r=subprocess.run([sys.executable,str(ROOT/'skills/humanizer-ru/scripts/scan.py'),'-','--before',str(p),'--json'],input='Цена 5 рублей.',text=True,capture_output=True)
            self.assertNotIn('Traceback',r.stderr)
            self.assertIn('facts',json.loads(r.stdout))

if __name__ == '__main__': unittest.main()
