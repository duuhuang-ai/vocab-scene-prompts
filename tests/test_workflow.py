import copy
import json
import sys
import unittest
import uuid
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT
sys.path.insert(0,str(SKILL/'scripts'))
from prepare_vocab import prepare
from compile_prompts import compile_project
from validate_project import validate, validate_snapshot, calculate_coverage

EXAMPLE=json.loads((SKILL/'references/restaurant.example.json').read_text())
RUN=ROOT/'.work'/('test-'+uuid.uuid4().hex[:10])
RUN.mkdir(parents=True,exist_ok=False)

class WorkflowTests(unittest.TestCase):
    def test_01_example_compilation(self):
        source=copy.deepcopy(EXAMPLE)
        originals=copy.deepcopy(source['source_entries'])
        result=compile_project(source)
        self.assertEqual(result['source_entries'],originals)
        self.assertTrue(validate(result)['planning_complete_for_scope'])
        for page in result['pages']:
            self.assertIn(result['style_profile']['positive_prompt'],page['prompt']['ready_to_copy'])
            self.assertIn('账单夹',page['prompt']['ready_to_copy'])

    def test_02_xlsx_duplicates_and_whitespace(self):
        from openpyxl import Workbook
        wb=Workbook(); ws=wb.active; ws.title='Words'
        ws.append(['序号','单词','音标','释义','备注'])
        ws.append([1,' bread ','/bred/','n. 面包','keep extra column'])
        ws.append([2,' bread ','/bred/','n. 面包','second record'])
        path=RUN/'duplicates.xlsx'; wb.save(path)
        project=RUN/'duplicates.json'; snapshot=RUN/'duplicates-snapshot.json'
        prepare(path,project,snapshot,sheet='Words')
        data=json.loads(project.read_text()); snap=json.loads(snapshot.read_text())
        self.assertEqual(len(data['source_entries']),2)
        self.assertEqual(data['source_entries'][0]['original']['word'],' bread ')
        self.assertNotEqual(data['source_entries'][0]['id'],data['source_entries'][1]['id'])
        self.assertEqual(snap['rows'][2][4],'second record')
        self.assertFalse(validate(data)['planning_complete_for_scope'])
        validate_snapshot(data,snap)
        data['source_entries'][0]['original']['word']='bread'
        with self.assertRaises(ValueError): validate_snapshot(data,snap)

    def test_03_word_only_pending(self):
        source=RUN/'word-only.txt';source.write_text('bread\nsoup\n')
        output=RUN/'word-only.json';snapshot=RUN/'word-only-snapshot.json'
        prepare(source,output,snapshot)
        data=json.loads(output.read_text())
        self.assertIsNone(data['source_entries'][0]['original']['phonetic'])
        self.assertEqual(data['source_entries'][0]['source_locator']['row'],1)
        self.assertEqual(len(validate(data)['coverage']['pending_entry_ids']),2)

    def test_04_verified_missing_field_supplement(self):
        d=copy.deepcopy(EXAMPLE);entry=d['source_entries'][6];eid=entry['id']
        d['source_entries']=[entry];entry['original']['phonetic']=None;entry['original']['meaning']=None
        d['classifications']=[next(c for c in d['classifications'] if c['entry_id']==eid)]
        d['supplements']=[{'entry_id':eid,'phonetic':'/bred/','meaning':'n. 面包','part_of_speech':'n.',
            'evidence':'fixture: validator behavior only','verification_status':'verified'}]
        p=d['pages'][0];p['vocabulary']=[next(v for v in p['vocabulary'] if v['entry_id']==eid)]
        p['layout']=p['layout'][:1];p['layout'][0]['vocabulary_entry_ids']=[eid]
        d['coverage']=calculate_coverage(d)
        compile_project(d)
        self.assertIsNone(d['source_entries'][0]['original']['meaning'])
        d['supplements'][0]['verification_status']='pending_review'
        with self.assertRaises(ValueError): compile_project(d)

    def test_05_duplicate_first_rejected(self):
        d=copy.deepcopy(EXAMPLE);p=copy.deepcopy(d['pages'][0]);p['id']='page-002';p['page_number']=2;d['pages'].append(p)
        with self.assertRaises(ValueError): compile_project(d)

    def test_06_missing_classification_rejected(self):
        d=copy.deepcopy(EXAMPLE);d['classifications'].pop()
        with self.assertRaises(ValueError): compile_project(d)

    def test_07_cross_reference_rejected(self):
        d=copy.deepcopy(EXAMPLE);d['pages'][0]['layout'][0]['vocabulary_entry_ids']=['unknown-id']
        with self.assertRaises(ValueError): compile_project(d)

    def test_08_wrong_text_and_omitted_style_rejected(self):
        for mutate in [lambda d:d['pages'][0]['vocabulary'][0].update(display_phonetic='/bad/'),
                       lambda d:d['pages'][0]['prompt'].update(ready_to_copy='同上')]:
            d=copy.deepcopy(EXAMPLE);mutate(d)
            with self.assertRaises(ValueError):validate(d)

    def test_09_review_order_and_reason(self):
        d=copy.deepcopy(EXAMPLE);p=copy.deepcopy(d['pages'][0]);p['id']='page-002';p['page_number']=2
        for v in p['vocabulary']:v['teaching_role']='review';v['review_reason']='复习本场景词汇'
        d['pages'].append(p);compile_project(d)
        self.assertEqual(d['coverage']['review_occurrence_count'],12)
        p['page_number']=0
        with self.assertRaises(ValueError):compile_project(d)

    def test_10_exported_text_roundtrip(self):
        from export_prompts import export
        out=RUN/'export'
        export(compile_project(copy.deepcopy(EXAMPLE)),out)
        exported=json.loads((out/'project.json').read_text())
        with ZipFile(out/'分页生图提示词.docx') as z:
            xml=ET.fromstring(z.read('word/document.xml'))
        text='\n'.join(n.text or '' for n in xml.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
        prompt=exported['pages'][0]['prompt']['ready_to_copy']
        self.assertIn(''.join(prompt.split()),''.join(text.split()))
        self.assertIn(prompt,(out/'分页生图提示词.md').read_text())

    def test_11_csv_and_json_inputs(self):
        for name,content in [('input.csv','word,phonetic,meaning\nbread,/bred/,n. 面包\n'),
                             ('input.json',json.dumps([{'word':'bread','phonetic':'/bred/','meaning':'n. 面包'}]))]:
            source=RUN/name;source.write_text(content)
            prepare(source,RUN/(name+'-project.json'),RUN/(name+'-snapshot.json'))
            self.assertEqual(json.loads((RUN/(name+'-project.json')).read_text())['source_entries'][0]['original']['word'],'bread')

    def test_12_blank_word_and_formula_rejected(self):
        for name,content in [('bad.csv','word,phonetic,meaning\n,/bred/,n. 面包\n')]:
            source=RUN/name;source.write_text(content)
            with self.assertRaises(ValueError):prepare(source,RUN/'bad-project.json',RUN/'bad-snapshot.json')
        from openpyxl import Workbook
        w=Workbook();s=w.active;s.append(['word','phonetic','meaning']);s.append(['bread','=A2','n. 面包'])
        source=RUN/'formula.xlsx';w.save(source)
        with self.assertRaises(ValueError):prepare(source,RUN/'formula-project.json',RUN/'formula-snapshot.json')

if __name__=='__main__': unittest.main(verbosity=2)
