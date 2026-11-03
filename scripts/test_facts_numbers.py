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
        p=subprocess.run(['node','-e',source],cwd=ROOT,text=True,encoding='utf-8',capture_output=True,check=True)
        self.assertEqual(json.loads(p.stdout),[numeric_facts(t) for t in texts])

    def test_swapped_numbers(self):
        for a,b in [('Анна получила 30 000 рублей, Борис 50 000 рублей.', 'Анна получила 50 000 рублей, Борис 30 000 рублей.'),
                    ('Анна получила 30 000 и Борис 50 000.', 'Анна получила 50 000 и Борис 30 000.'),
                    ('Выручка 10, прибыль 2.', 'Выручка 2, прибыль 10.'),
                    ('Выручка выросла на 10%. Прибыль упала на 2%.', 'Выручка упала на 2%. Прибыль выросла на 10%.'),
                    ('Анна получила 30 рублей, Борис 50 долларов.', 'Анна получила 50 долларов, Борис 30 рублей.'),
                    ('В марте пришло 40 клиентов, в мае 70 клиентов, в июле 90 клиентов.', 'В марте пришло 70 клиентов, в мае 90 клиентов, в июле 40 клиентов.')]:
            with self.subTest(a=a, b=b):
                self.assertTrue(diff_facts(a,b).swapped)
    def test_not_swapped(self):
        for a,b in [('Анна получила 30 рублей, Борис 50 рублей.', 'Борис получил 50 рублей, Анна 30 рублей.'),
                    ('Цена 1,5 млн, срок 10 дней.', 'Срок 10 дней, цена 1,5 млн.'),
                    ('Анна получила 30, Борис 30.', 'Борис получил 30, Анна 30.'),
                    ('Встреча 10.05.2026 в зале 7.', 'В зале 7 встреча 10.05.2026.')]:
            with self.subTest(a=a, b=b):
                self.assertEqual(diff_facts(a,b).swapped, [])
    def test_quotes_compared(self):
        d = diff_facts('Директор сказал: «нам придётся закрыть цех».', 'Директор сказал: «нам надо закрыть цех».')
        self.assertIn('цитата:«нам придется закрыть цех»', d.lost)
        self.assertIn('цитата:«нам надо закрыть цех»', d.claims_added)
        same = diff_facts('Он сказал: «нам придётся закрыть цех».', 'Сказал он: «Нам придется **закрыть** цех!»')
        self.assertFalse([x for x in same.lost + same.claims_added if x.startswith('цитата:')])
        short = diff_facts('Пекарня «Колос» открыта.', 'Пекарня открыта.')
        self.assertFalse([x for x in short.lost if x.startswith('цитата:')])
    def test_browser_swaps_and_quotes(self):
        cases=[('Анна получила 30 000 рублей, Борис 50 000 рублей.','Анна получила 50 000 рублей, Борис 30 000 рублей.'),
               ('Анна получила 30 рублей, Борис 50 рублей.','Борис получил 50 рублей, Анна 30 рублей.'),
               ('Он сказал: «нам придётся закрыть цех».','Он сказал: «нам надо закрыть цех».')]
        source="const fs=require('fs'),vm=require('vm');for(const f of ['scan-rules','scan','facts'])vm.runInThisContext(fs.readFileSync('docs/'+f+'.js','utf8'));const cases="+json.dumps(cases)+";process.stdout.write(JSON.stringify(cases.map(([a,b])=>humanizerFacts.factsDiff(a,b))));"
        p=subprocess.run(['node','-e',source],cwd=ROOT,text=True,encoding='utf-8',capture_output=True,check=True)
        swap,clean,quote=json.loads(p.stdout)
        self.assertEqual(len(swap['swapped']),1)
        self.assertEqual(clean['swapped'],[])
        self.assertTrue(any('цитата' in x for x in quote['lost']))
        self.assertTrue(any('цитата' in x for x in quote['claimsAdded']))

    def test_empty_before_json(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'before';p.write_text('')
            r=subprocess.run([sys.executable,str(ROOT/'skills/humanizer-ru/scripts/scan.py'),'-','--before',str(p),'--json'],input='Цена 5 рублей.',text=True,encoding='utf-8',capture_output=True)
            self.assertNotIn('Traceback',r.stderr)
            self.assertIn('facts',json.loads(r.stdout))

if __name__ == '__main__': unittest.main()
