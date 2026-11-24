"""Validate the bundled project contract and cross-record invariants; no dependencies."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

SCHEMA_PATH=Path(__file__).resolve().parents[1]/'references/project.schema.json'

def require(condition, message):
    if not condition: raise ValueError(message)

def validate_structure(data, schema, root=None, path='$'):
    root=root or schema
    supported={'$schema','$defs','$ref','title','description','type','properties','required','additionalProperties',
               'items','minItems','uniqueItems','minLength','pattern','const','enum','minimum','maximum','exclusiveMinimum'}
    require(not set(schema)-supported, f'{path}: unsupported schema keywords {set(schema)-supported}')
    if '$ref' in schema:
        target=root
        for key in schema['$ref'].split('/')[1:]: target=target[key]
        return validate_structure(data,target,root,path)
    types={'object':lambda v:isinstance(v,dict),'array':lambda v:isinstance(v,list),
           'string':lambda v:isinstance(v,str),'integer':lambda v:isinstance(v,int) and not isinstance(v,bool),
           'number':lambda v:isinstance(v,(int,float)) and not isinstance(v,bool),
           'null':lambda v:v is None,'boolean':lambda v:isinstance(v,bool)}
    if 'type' in schema:
        expected=schema['type'] if isinstance(schema['type'],list) else [schema['type']]
        require(any(types[t](data) for t in expected),f'{path}: expected {expected}')
    if 'const' in schema: require(data==schema['const'],f'{path}: wrong constant')
    if 'enum' in schema: require(data in schema['enum'],f'{path}: invalid enum')
    if isinstance(data,dict):
        props=schema.get('properties',{})
        require(set(schema.get('required',[]))<=set(data),f'{path}: missing required fields')
        if schema.get('additionalProperties') is False: require(set(data)<=set(props),f'{path}: unknown fields')
        for k,v in data.items():
            if k in props: validate_structure(v,props[k],root,path+'.'+k)
    if isinstance(data,list):
        require(len(data)>=schema.get('minItems',0),f'{path}: too few items')
        if schema.get('uniqueItems'): require(len({json.dumps(v,sort_keys=True) for v in data})==len(data),f'{path}: duplicate items')
        for i,v in enumerate(data): validate_structure(v,schema.get('items',{}),root,f'{path}[{i}]')
    if isinstance(data,str):
        require(len(data)>=schema.get('minLength',0),f'{path}: empty string')
        if 'pattern' in schema: require(re.search(schema['pattern'],data) is not None,f'{path}: pattern mismatch')
    if isinstance(data,(int,float)) and not isinstance(data,bool):
        for keyword,operation in [('minimum',lambda a,b:a>=b),('maximum',lambda a,b:a<=b),('exclusiveMinimum',lambda a,b:a>b)]:
            if keyword in schema: require(operation(data,schema[keyword]),f'{path}: bound failed')

def unique(rows,key):
    values=[r[key] for r in rows]
    require(len(values)==len(set(values)),f'duplicate {key}')
    return {r[key]:r for r in rows}

def effective_fields(data, entry):
    rows=[s for s in data['supplements'] if s['entry_id']==entry['id'] and s['verification_status']=='verified']
    supplement=rows[0] if rows else {}
    return {k:entry['original'][k] or supplement.get(k) for k in ['word','phonetic','meaning']}

def pending_ids(data):
    pending={e['id'] for e in data['source_entries'] if e['review_status']=='pending_review'}
    pending.update(c['entry_id'] for c in data['classifications'] if c['review_status']=='pending_review')
    return pending

def calculate_coverage(data):
    ids={e['id'] for e in data['source_entries']}
    first={v['entry_id'] for p in data['pages'] for v in p['vocabulary'] if v['teaching_role']=='first'}
    return {'scope_entry_count':len(ids),'classified_count':len(data['classifications']),
            'first_teaching_count':len(first),'pending_entry_ids':sorted(pending_ids(data)),
            'unplaced_entry_ids':sorted(ids-first),
            'review_occurrence_count':sum(v['teaching_role']=='review' for p in data['pages'] for v in p['vocabulary'])}

def validate(data,check_prompts=True):
    schema=json.loads(SCHEMA_PATH.read_text())
    validate_structure(data,schema)
    entries=unique(data['source_entries'],'id'); themes=unique(data['themes'],'id')
    classes=unique(data['classifications'],'entry_id')
    require(set(entries)==set(classes),'classification coverage differs from source scope')
    unique(data['pages'],'id'); unique(data['pages'],'page_number')
    unique(data['supplements'],'entry_id')
    for sup in data['supplements']:
        require(sup['entry_id'] in entries,'unknown supplement source')
        for k in ['phonetic','meaning']:
            require(not sup[k] or not entries[sup['entry_id']]['original'][k],f'supplement may not override original {k}')
    pending=pending_ids(data)
    for eid,c in classes.items():
        require(c['theme_id'] in themes,'unknown classification theme')
        f=effective_fields(data,entries[eid])
        if eid not in pending:
            require(f['phonetic'] and f['meaning'] and c['selected_meaning'] and c['part_of_speech'],f'{eid}: missing teaching fields')
            require(c['selected_meaning'] in f['meaning'],f'{eid}: selected meaning absent from source or verified supplement')
            supplement=next((s for s in data['supplements'] if s['entry_id']==eid and s['verification_status']=='verified'),{})
            require(c['part_of_speech'] in f['meaning'] or c['part_of_speech']==supplement.get('part_of_speech'),f'{eid}: POS unsupported')
    cfg=data['project']['defaults']; a,b=map(int,cfg['aspect_ratio'].split(':'))
    require(cfg['width']*b==cfg['height']*a,'image dimensions disagree with aspect ratio')
    require(cfg['target_min_words']<=cfg['target_max_words'],'invalid word count recommendation')
    first_pages={}; first_counts=Counter(); char_defs={}; warnings=[]
    for p in sorted(data['pages'],key=lambda p:p['page_number']):
        require(p['theme_id'] in themes,'unknown page theme')
        require(p['style_profile_id']==data['style_profile']['id'],'unknown style profile')
        chars=unique(p['characters'],'id'); items=unique(p['vocabulary'],'entry_id')
        scenes=unique(p['layout'],'id'); unique(p['layout'],'order')
        require(sorted(s['order'] for s in scenes.values())==list(range(1,len(scenes)+1)),'scene order must be contiguous')
        require(sum(s['relative_height'] for s in scenes.values())<=1.000001,'scene area exceeds full page')
        assigned=set()
        for s in scenes.values():
            require(set(s['character_ids'])<=set(chars),'unknown scene character')
            require(set(s['vocabulary_entry_ids'])<=set(items),'unknown scene vocabulary')
            assigned.update(s['vocabulary_entry_ids'])
        require(assigned==set(items),'scene vocabulary coverage mismatch')
        for cid,c in chars.items():
            if cid in char_defs: require(char_defs[cid]==c['description'],'same character id changed appearance; explain as separate design')
            char_defs[cid]=c['description']
        for eid,v in items.items():
            require(eid in entries,'unknown page source')
            c=classes[eid]; f=effective_fields(data,entries[eid])
            require(c['theme_id']==p['theme_id'],'page theme differs from classification')
            for field,value in [('word',f['word']),('phonetic',f['phonetic']),('meaning',c['selected_meaning']),('part_of_speech',c['part_of_speech'])]:
                require(v['display_'+field]==value,f'{eid}: display {field} differs from teaching source')
            if p['status']=='prompt_ready': require(eid not in pending,'pending vocabulary in ready page')
            if v['teaching_role']=='first':
                first_counts[eid]+=1; require(first_counts[eid]==1,'duplicate first teaching')
                first_pages[eid]=p['page_number']; require(not v['review_reason'],'first teaching has review reason')
            else:
                require(v['review_reason'],'review reason missing')
                require(first_pages.get(eid,10**20)<p['page_number'],'review precedes first teaching')
        if not cfg['target_min_words']<=len(items)<=cfg['target_max_words']:
            warnings.append(f"{p['id']}: {len(items)} words outside recommendation; review composition_notes")
        if check_prompts and p['status']=='prompt_ready':
            prompt=p['prompt']['ready_to_copy']
            require('同上' not in prompt,'prompt contains an abbreviation')
            for text in [p['title'],p['subtitle'],data['style_profile']['positive_prompt'],data['style_profile']['negative_prompt']]:
                require(text in prompt,'full title/style missing in prompt')
            require(p['prompt']['negative_prompt']==data['style_profile']['negative_prompt'],'negative prompt drift')
            for v in items.values():
                for k in ['display_word','display_phonetic','display_meaning','display_part_of_speech','visual_target','label_position']:
                    require(v[k] in prompt,f'prompt omitted {k}')
            for s in scenes.values(): require(s['scene_description'] in prompt,'scene omitted from prompt')
    expected=calculate_coverage(data)
    for k,v in expected.items():
        if isinstance(v,list): require(set(v)==set(data['coverage'][k]),f'coverage mismatch: {k}')
        else: require(v==data['coverage'][k],f'coverage mismatch: {k}')
    complete=not pending and not expected['unplaced_entry_ids'] and all(p['status']=='prompt_ready' for p in data['pages'])
    return {'valid':True,'planning_complete_for_scope':complete,'scope':data['project']['scope'],
            'pages':len(data['pages']),'coverage':expected,'warnings':warnings,
            'validation':'bundled contract structure and cross-record semantics'}

def validate_snapshot(data,snapshot):
    originals={e['id']:e['original'] for e in data['source_entries']}
    require(originals==snapshot['original_records'],'original fields differ from input snapshot')
    require(data['project'].get('source_sha256')==snapshot['sha256'],'source hash differs from snapshot')

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('project'); p.add_argument('--snapshot'); a=p.parse_args()
    try:
        data=json.loads(Path(a.project).read_text()); result=validate(data)
        if a.snapshot:
            validate_snapshot(data,json.loads(Path(a.snapshot).read_text())); result['source_snapshot_matches']=True
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,KeyError,TypeError) as e: p.exit(1,str(e)+'\n')

if __name__=='__main__': main()
