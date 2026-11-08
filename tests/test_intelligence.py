import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from splitwise_receipts import intelligence as ai
from splitwise_receipts.server import Scan, app
from fastapi.testclient import TestClient


def receipt():
    return dict(description='Cafe', currency='USD', tax='0.00', tip='0.00', discount='0.00', receipt_total='18.00', warnings=[], items=[dict(name='Burger', amount='18.00', people=[1])])


class Validation(unittest.TestCase):
    def test_reject_unknown_people(self):
        r=receipt();r['items'][0]['people']=[999]
        with self.assertRaisesRegex(ValueError,'participant'):ai.validate_receipt(r,[{'id':1}])

    def test_reject_duplicate_people(self):
        r=receipt();r['items'][0]['people']=[1,1]
        with self.assertRaises(ValueError):ai.validate_receipt(r,[{'id':1}])

    def test_invalid_amounts(self):
        for field in ['tax','tip','discount']:
            r=receipt();r[field]='-1.00'
            with self.assertRaises(ValueError):ai.validate_receipt(r,[{'id':1}])
        r=receipt();r['items'][0]['amount']='NaN'
        with self.assertRaises(ValueError):ai.validate_receipt(r,[{'id':1}])

    def test_ambiguous_assignment_can_be_reviewed(self):
        r=receipt();r['items'][0]['people']=[];r['warnings']=['Ambiguous person.']
        self.assertEqual(ai.validate_receipt(r,[{'id':1}])['items'][0]['people'],[])


class Codex(unittest.IsolatedAsyncioTestCase):
    async def test_signed_out(self):
        with patch.object(ai,'codex_status',AsyncMock(return_value={'ready':False,'message':'Sign in first.'})):
            with self.assertRaisesRegex(ValueError,'Sign in first'):await ai.codex_scan(Scan(),b'','')

    async def test_isolated_schema_and_secret_free_environment(self):
        captured={}
        async def fake_exec(*args,**kwargs):
            captured['args']=args;captured['kwargs']=kwargs
            output=Path(args[args.index('-o')+1]);output.write_text(json.dumps(receipt()))
            captured['folder']=output.parent
            self.assertTrue(Path(args[args.index('--output-schema')+1]).exists())
            return SimpleNamespace(returncode=0,communicate=AsyncMock(return_value=(None,None)))
        with patch.object(ai,'codex_status',AsyncMock(return_value={'ready':True})),patch.object(ai,'codex_binary',return_value='/test/codex'),patch.object(ai.asyncio,'create_subprocess_exec',fake_exec),patch.dict(ai.os.environ,{'SPLITWISE_API_KEY':'secret','OPENAI_API_KEY':'secret','CANVAS_ACCESS_TOKEN':'secret'}):
            result=await ai.codex_scan(Scan(text='Burger 18.00',people=[{'id':1}]),b'','')
        self.assertEqual(result['receipt_total'],'18.00')
        self.assertNotIn('SPLITWISE_API_KEY',captured['kwargs']['env'])
        self.assertNotIn('OPENAI_API_KEY',captured['kwargs']['env'])
        self.assertNotIn('CANVAS_ACCESS_TOKEN',captured['kwargs']['env'])
        self.assertIn('--ignore-user-config',captured['args'])
        self.assertIn('read-only',captured['args'])
        self.assertIn('shell_tool',captured['args'])
        self.assertFalse(captured['folder'].exists())

    async def test_failure_does_not_expose_stderr(self):
        async def fake_exec(*args,**kwargs):return SimpleNamespace(returncode=1,communicate=AsyncMock(return_value=(None,None)))
        with patch.object(ai,'codex_status',AsyncMock(return_value={'ready':True})),patch.object(ai,'codex_binary',return_value='/test/codex'),patch.object(ai.asyncio,'create_subprocess_exec',fake_exec):
            with self.assertRaisesRegex(ValueError,'Nothing was posted'):await ai.codex_scan(Scan(),b'','')


class Routing(unittest.TestCase):
    def test_chatgpt_instructions_without_photo(self):
        with patch('splitwise_receipts.server.codex_scan',AsyncMock(return_value=receipt())) as reader:
            with TestClient(app) as client:
                response=client.post('/api/scan',json={'reader':'chatgpt','instructions':'I had a burger for 18 dollars.','people':[{'id':1}]})
        self.assertEqual(response.status_code,200,response.text)
        reader.assert_awaited_once()

    def test_invalid_reader_rejected(self):
        with TestClient(app) as client:
            self.assertEqual(client.post('/api/scan',json={'reader':'shell'}).status_code,422)
