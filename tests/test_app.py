import asyncio
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from splitwise_receipts.core import allocate, calculate, cents, parse_text
from splitwise_receipts import server


def example():
    return dict(description='Dinner', currency='USD', date='2026-11-07', group_id=0, payer_id=1,
                people=[dict(id=1,name='You'),dict(id=2,name='Alex'),dict(id=3,name='Sam')],
                items=[dict(name='Burger',amount='18.00',people=[1]),dict(name='Salad',amount='14.00',people=[2]),dict(name='Fries',amount='9.00',people=[1,2,3])],
                tax='4.10', tip='8.20', discount='0.00', receipt_total='53.30')


class Arithmetic(unittest.TestCase):
    def test_itemized_tax_tip(self):
        result=calculate(example())
        self.assertEqual(result['total'],'53.30')
        self.assertEqual([p['owed'] for p in result['shares']],['27.30','22.10','3.90'])
        self.assertEqual(sum(cents(p['paid']) for p in result['shares']),5330)

    def test_rounding_conserves_cents(self):
        rng=random.Random(42)
        for _ in range(2000):
            weights=[rng.randint(0,50000) for _ in range(rng.randint(1,30))]
            if not sum(weights): continue
            amount=rng.randint(-1000000,1000000)
            result=allocate(amount,weights)
            self.assertEqual(sum(result),amount)
            self.assertTrue(all(n==0 for n,w in zip(result,weights) if w==0))

    def test_invalid_money(self):
        for value in ['NaN','Infinity','1.001','-Infinity','999999999999']:
            with self.assertRaises(ValueError):cents(value)

    def test_bad_assignments(self):
        for assignment in [[],[999],[1,1]]:
            d=example();d['items'][0]['people']=assignment
            with self.assertRaises(ValueError):calculate(d)

    def test_total_mismatch(self):
        d=example();d['receipt_total']='60.00'
        with self.assertRaisesRegex(ValueError,'Correct the receipt'):calculate(d)

    def test_discount(self):
        d=example();d['discount']='4.10';d['receipt_total']='49.20'
        r=calculate(d)
        self.assertEqual(sum(cents(s['owed']) for s in r['shares']),4920)
        self.assertTrue(all(cents(s['owed'])>=0 for s in r['shares']))

    def test_local_parser(self):
        r=parse_text('CAFE\nBurger 18.00\nSalad 14.00\nFries 9.00\nSubtotal 41.00\nTax 4.10\nTip 8.20\nTotal 53.30\nVISA 53.30')
        self.assertEqual(len(r['items']),3)
        self.assertEqual(r['receipt_total'],'53.30')
        self.assertEqual(r['tax'],'4.10')


class App(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.dbpatch=patch.object(server,'DB',Path(self.temp.name)/'test.sqlite3');self.dbpatch.start()
        self.configpatch=patch.object(server,'CONFIG',Path(self.temp.name)/'credentials.json');self.configpatch.start()
        self.client=TestClient(server.app)
        self.calls=[]
        self.uncertain=False
        self.identity=1
        async def fake(path,payload=None,key=None):
            self.calls.append((path,payload))
            if path=='get_current_user':return {'user':{'id':self.identity,'first_name':'You','default_currency':'USD'}}
            if path=='get_friends':return {'friends':[{'id':2,'first_name':'Alex'},{'id':3,'first_name':'Sam'}]}
            if path=='get_groups':return {'groups':[]}
            if path=='get_currencies':return {'currencies':[{'currency_code':'USD'}]}
            if path=='create_expense':
                if self.uncertain:raise server.HTTPException(502,'Network timed out')
                return {'expenses':[{'id':123}],'errors':{}}
            raise AssertionError(path)
        self.patch=patch.object(server,'splitwise',fake);self.patch.start()

    def tearDown(self):
        self.patch.stop();self.dbpatch.stop();self.configpatch.stop();self.temp.cleanup()

    def test_home_and_offline(self):
        self.assertEqual(self.client.get('/').status_code,200)
        r=self.client.post('/api/calculate',json=example())
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['total'],'53.30')
        self.assertEqual(self.calls,[])

    def test_security(self):
        self.assertEqual(self.client.post('/api/calculate',json=example(),headers={'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.client.get('/',headers={'Host':'evil.test'}).status_code,400)
        self.assertEqual(self.client.post('/api/settings',content='x',headers={'Content-Type':'text/plain'}).status_code,415)

    def test_preview_submit_idempotency(self):
        r=self.client.post('/api/preview',json=example())
        self.assertEqual(r.status_code,200,r.text)
        token=r.json()['preview_id']
        self.assertFalse(any(p=='create_expense' for p,_ in self.calls))
        again=self.client.post('/api/preview',json=example()).json()
        self.assertEqual(again['preview_id'],token)
        for _ in range(2):
            s=self.client.post('/api/submit',json={'preview_id':token})
            self.assertEqual(s.status_code,200,s.text)
            self.assertEqual(s.json()['expense_id'],123)
        writes=[payload for path,payload in self.calls if path=='create_expense']
        self.assertEqual(len(writes),1)
        self.assertEqual(writes[0]['users__1__owed_share'],'22.10')
        self.assertEqual(writes[0]['users__0__paid_share'],'53.30')

    def test_uncertain_post_blocks_retry(self):
        token=self.client.post('/api/preview',json=example()).json()['preview_id']
        self.uncertain=True
        self.assertEqual(self.client.post('/api/submit',json={'preview_id':token}).status_code,502)
        self.assertEqual(self.client.post('/api/submit',json={'preview_id':token}).status_code,409)
        self.assertEqual(len([1 for p,_ in self.calls if p=='create_expense']),1)

    def test_account_change_blocks_post(self):
        token=self.client.post('/api/preview',json=example()).json()['preview_id']
        self.identity=2
        self.assertEqual(self.client.post('/api/submit',json={'preview_id':token}).status_code,422)

    def test_scan_and_invalid_upload(self):
        r=self.client.post('/api/scan',json={'text':'CAFE\nBurger 18.00','people':[{'id':1}], 'instructions':'Alex had burger'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['items'][0]['people'],[1])
        self.assertTrue(any('not applied' in w for w in r.json()['warnings']))
        self.assertEqual(self.client.post('/api/scan',json={'image':'data:image/png;base64,aGVsbG8='}).status_code,422)

    def test_secret_not_returned(self):
        r=self.client.post('/api/settings',json={'splitwise_key':'test-secret','openai_key':'test-ai-secret'})
        self.assertEqual(r.status_code,200)
        self.assertNotIn('test-secret',r.text)
        self.assertNotIn('test-ai-secret',self.client.get('/api/status').text)
        self.assertEqual(server.CONFIG.stat().st_mode & 0o777,0o600)


if __name__=='__main__':unittest.main()
