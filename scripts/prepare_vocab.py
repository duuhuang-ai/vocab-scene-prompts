"""Read a vocabulary source without classifying it or changing source strings."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

REF = Path(__file__).resolve().parents[1] / 'references'
ALIASES = {'word': ['word','单词','词汇','英文'], 'phonetic': ['phonetic','ipa','音标'],
           'meaning': ['meaning','definition','释义','中文释义','中文'], 'serial': ['serial','序号','编号']}

def resolve_columns(headers, overrides):
    normalized = [str(x).strip().lower() if x is not None else '' for x in headers]
    result = {}
    for field, aliases in ALIASES.items():
        expected = [overrides[field].strip().lower()] if overrides[field] else aliases
        indices = [i for i,h in enumerate(normalized) if h in expected]
        if len(indices)>1: raise ValueError(f'Ambiguous {field} columns; provide an explicit column name')
        result[field] = indices[0] if indices else None
        if overrides[field] and not indices: raise ValueError(f'Column not found: {overrides[field]}')
    if result['word'] is None: raise ValueError('Word column not identified; specify --word-column')
    return result

def read_rows(path, sheet, overrides):
    suffix=path.suffix.lower()
    selected=None
    if suffix=='.xlsx':
        from openpyxl import load_workbook
        wb=load_workbook(path,read_only=True,data_only=False)
        if not sheet and len(wb.sheetnames)!=1: raise ValueError('Multiple sheets: specify --sheet')
        selected=sheet or wb.sheetnames[0]
        rows=[list(r) for r in wb[selected].iter_rows(values_only=True)]
        wb.close()
    elif suffix in ['.csv','.tsv']:
        with path.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.reader(f,delimiter='\t' if suffix=='.tsv' else ','))
    elif suffix=='.txt':
        rows=[['word']]+[[line] for line in path.read_text(encoding='utf-8-sig').splitlines()]
    elif suffix=='.json':
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data,list): raise ValueError('JSON input must be an array')
        if all(isinstance(x,str) for x in data): rows=[['word']]+[[x] for x in data]
        elif all(isinstance(x,dict) for x in data):
            headers=list(dict.fromkeys(k for x in data for k in x))
            rows=[headers]+[[x.get(k) for k in headers] for x in data]
        else: raise ValueError('Use either string records or object records consistently')
    else: raise ValueError('Use xlsx/csv/tsv/txt/json; extract Word tables to JSON first')
    if len(rows)<2: raise ValueError('No vocabulary records')
    columns=resolve_columns(rows[0],overrides)
    records=[]
    for number,row in enumerate(rows[1:],start=2):
        if all(v is None or v=='' for v in row): continue
        values={k: (row[i] if i is not None and i<len(row) else None) for k,i in columns.items()}
        if values['word'] is None or not str(values['word']).strip(): raise ValueError(f'Non-empty row {number} has no word; resolve it first')
        for k in ['word','phonetic','meaning']:
            value=values[k]
            if value=='': values[k]=None
            elif value is not None and not isinstance(value,str): raise ValueError(f'Expected text in {k}, row {number}')
            if suffix=='.xlsx' and isinstance(value,str) and value.startswith('='):
                raise ValueError(f'Formula in teaching field at row {number}; supply readable values')
        records.append((number-1 if suffix in ['.txt','.json'] else number,values))
    if not records: raise ValueError('No nonempty word records')
    return rows, records, selected

def prepare(source, output, snapshot, sheet=None, overrides=None):
    source,output,snapshot=map(Path,[source,output,snapshot])
    if output.exists() or snapshot.exists(): raise FileExistsError('Use new output and snapshot paths')
    if output.resolve()==snapshot.resolve(): raise ValueError('Project and snapshot need distinct paths')
    overrides=overrides or dict.fromkeys(ALIASES)
    rows,records,selected=read_rows(source,sheet,overrides)
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    entries=[]
    for row,v in records:
        entries.append({'id':f'entry-{row:06d}', 'source_locator':{'file':source.name,'sheet':selected,'row':row},
            'original':{'serial':v['serial'],'word':v['word'],'phonetic':v['phonetic'],'meaning':v['meaning']},
            'review_status':'ready' if v['phonetic'] and v['meaning'] else 'pending_review',
            'review_note':'' if v['phonetic'] and v['meaning'] else '原表缺字段；核对后补入supplements，保留原始空值。'})
    ids=[x['id'] for x in entries]
    data={'schema_version':'1.1.0', 'project':{'id':'vocab-'+sha[:12], 'title':source.stem+'场景漫画提示词',
        'scope':'full','source_name':source.name,'source_sha256':sha,'audience':'成人英语学习者','locale':'zh-CN',
        'defaults':{'aspect_ratio':'3:4','width':1536,'height':2048,'target_min_words':8,'target_max_words':12}},
        'style_profile':json.loads((REF/'style_profile.json').read_text()),'source_entries':entries,'supplements':[],
        'themes':[{'id':'pending','name':'待分类与复核','description':'由模型根据词义分类并规划页面。','scene_directions':['待规划']}],
        'classifications':[{'entry_id':x,'theme_id':'pending','selected_meaning':None,'part_of_speech':None,
            'reason':'尚未进行语义分类','review_status':'pending_review'} for x in ids], 'pages':[],
        'coverage':{'scope_entry_count':len(ids),'classified_count':len(ids),'first_teaching_count':0,
            'pending_entry_ids':ids,'unplaced_entry_ids':ids,'review_occurrence_count':0}}
    evidence={'source_file':source.name,'sha256':sha,'sheet':selected,'rows':rows,
              'source_row_numbers':[r for r,v in records],
              'original_records':{e['id']:e['original'] for e in entries}}
    for p in [output,snapshot]: p.parent.mkdir(parents=True,exist_ok=True)
    snapshot.write_text(json.dumps(evidence,ensure_ascii=False,indent=2,default=str)+'\n')
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    return {'records':len(entries),'status':'draft_needs_semantic_planning','output':str(output)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source'); p.add_argument('--sheet'); p.add_argument('--output',required=True); p.add_argument('--snapshot',required=True)
    for k in ALIASES: p.add_argument('--'+k+'-column')
    a=p.parse_args()
    try:
        result=prepare(a.source,a.output,a.snapshot,a.sheet,{k:getattr(a,k+'_column') for k in ALIASES})
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,FileExistsError,KeyError,ImportError) as e: p.exit(1,str(e)+'\n')

if __name__=='__main__': main()
