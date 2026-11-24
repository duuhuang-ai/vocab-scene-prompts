"""Export an already planned and validated project to editable Word, Markdown and JSON."""
import argparse
import json
from pathlib import Path
from validate_project import validate

def build_sections(data,report):
    themes={t['id']:t for t in data['themes']}
    entries={e['id']:e for e in data['source_entries']}
    blocks=[('title',data['project']['title']),('p',f"范围：{data['project']['scope']}；来源：{data['project']['source_name']}。范围内{len(entries)}条记录，{len(themes)}个主题，{len(data['pages'])}个漫画页面。"),
        ('p','文稿状态：'+('本次范围内分页文稿已完成。' if report['planning_complete_for_scope'] else '部分完成，见待处理清单。')),
        ('p','每个漫画页面对应一张图片，Word文档的物理页数可以更多。提示词就绪不代表生成图片已通过核对。'),
        ('p',f"覆盖情况：首次教学{report['coverage']['first_teaching_count']}条；复习{report['coverage']['review_occurrence_count']}次；待复核{len(report['coverage']['pending_entry_ids'])}条；未分页{len(report['coverage']['unplaced_entry_ids'])}条。"),('h1','主题总览')]
    rows=[]
    for t in data['themes']:
        ids=[c['entry_id'] for c in data['classifications'] if c['theme_id']==t['id']]
        rows.append([t['name'],str(len(ids)),'、'.join(t['scene_directions'])])
    blocks.append(('table',(['主题','记录数','场景方向'],rows)))
    blocks.append(('h1','漫画分页目录'))
    blocks.append(('table',(['页码','主题与标题','词数与状态'],[[str(p['page_number']),themes[p['theme_id']]['name']+' / '+p['subtitle'],str(len(p['vocabulary']))+' / '+p['status']] for p in data['pages']])))
    blocks.append(('h1','逐条分类清单'))
    blocks.append(('table',(['来源编号','原单词','主主题与选用义项'],[[c['entry_id'],entries[c['entry_id']]['original']['word'],themes[c['theme_id']]['name']+' / '+(c['selected_meaning'] or '待复核')] for c in data['classifications']])))
    blocks.append(('h1','逐页完整生图提示词'))
    for p in sorted(data['pages'],key=lambda p:p['page_number']):
        blocks.append(('page',f"第{p['page_number']:02d}页 {p['subtitle']}"))
        if p['status']=='prompt_ready': blocks.append(('prompt',p['prompt']['ready_to_copy']))
        else: blocks.append(('p','该页待复核，暂不作为可直接使用的生图指令。'))
    if report['coverage']['pending_entry_ids'] or report['coverage']['unplaced_entry_ids']:
        blocks.append(('h1','待处理清单'))
    for label,key in [('待复核','pending_entry_ids'),('未分页','unplaced_entry_ids')]:
        ids=report['coverage'][key]
        if ids: blocks.append(('p',label+'：'+'、'.join(x+' '+entries[x]['original']['word'] for x in ids)))
    for e in data['source_entries']:
        if e['id'] in report['coverage']['pending_entry_ids']: blocks.append(('p',e['id']+'：'+(e['review_note'] or '分类或资料仍待复核。')))
    if data['supplements']:
        blocks.append(('h1','补充资料来源'))
        blocks.append(('table',(['来源编号','补充内容','证据与状态'],[[s['entry_id'],' / '.join(s[k] for k in ['phonetic','meaning','part_of_speech'] if s[k]),s['evidence']+' / '+s['verification_status']] for s in data['supplements']])))
    return blocks

def markdown(blocks):
    out=[]
    for kind,value in blocks:
        if kind in ['title','h1','page']: out.extend([('# ' if kind=='title' else '## ')+value,''])
        elif kind=='table':
            headers,rows=value
            esc=lambda s:str(s).replace('|','\\|').replace('\n','<br>')
            out.extend(['| '+' | '.join(map(esc,headers))+' |','| '+' | '.join(['---']*len(headers))+' |'])
            out.extend('| '+' | '.join(map(esc,r))+' |' for r in rows); out.append('')
        elif kind=='prompt': out.extend(['```text',value,'```',''])
        else: out.extend([value,''])
    return '\n'.join(out)

def word(blocks,path):
    from docx import Document
    from docx.shared import Cm,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    doc=Document(); sec=doc.sections[0]
    sec.page_width,sec.page_height=Cm(21),Cm(29.7)
    sec.top_margin=sec.bottom_margin=Cm(1.8); sec.left_margin=sec.right_margin=Cm(2)
    for name,size in [('Normal',10.5),('Title',22),('Heading 1',17),('Heading 2',12)]:
        s=doc.styles[name]; s.font.name='Arial'; s.font.size=Pt(size); s.font.color.rgb=RGBColor(0,0,0)
        s.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'Songti SC')
        s.paragraph_format.line_spacing=Pt(16 if name=='Normal' else size+7)
        s.paragraph_format.space_after=Pt(5 if name=='Normal' else 8)
    for border in list(doc.styles.element.iter(qn('w:pBdr'))): border.getparent().remove(border)
    for kind,value in blocks:
        if kind=='table':
            headers,rows=value; t=doc.add_table(rows=1,cols=len(headers)); t.autofit=False
            widths=[5,2,10] if headers[1]=='记录数' else [4,5,8]
            for col,w in zip(t.columns,widths): col.width=Cm(w)
            for cell,w,txt in zip(t.rows[0].cells,widths,headers): cell.width=Cm(w); cell.text=txt
            t.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
            for row in rows:
                for cell,w,txt in zip(t.add_row().cells,widths,row): cell.width=Cm(w); cell.text=txt
            for ri,row in enumerate(t.rows):
                row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
                for cell in row.cells:
                    cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    pr=cell._tc.get_or_add_tcPr(); borders=OxmlElement('w:tcBorders')
                    for side in ['top','bottom','left','right']:
                        b=OxmlElement('w:'+side)
                        for k,v in [('val','single'),('sz','4'),('color','D9D9D9')]: b.set(qn('w:'+k),v)
                        borders.append(b)
                    pr.append(borders)
                    if ri==0:
                        sh=OxmlElement('w:shd'); sh.set(qn('w:fill'),'E7EDF2'); pr.append(sh)
                    for p in cell.paragraphs:
                        p.paragraph_format.space_before=Pt(3);p.paragraph_format.space_after=Pt(3)
                        for r in p.runs: r.bold=ri==0
            doc.add_paragraph()
        elif kind=='prompt':
            for piece in value.split('\n\n'): doc.add_paragraph(piece)
        else:
            if kind=='h1' and value=='逐页完整生图提示词': continue
            p=doc.add_paragraph(value,style={'title':'Title','h1':'Heading 1','page':'Heading 2'}.get(kind,'Normal'))
            if kind=='page': p.paragraph_format.page_break_before=True
    doc.core_properties.title=blocks[0][1]; doc.core_properties.author=''
    doc.save(path)

def export(data,outdir):
    report=validate(data)
    out=Path(outdir)
    if out.exists(): raise FileExistsError('Output directory exists; use a new version directory')
    # Verify Word support before creating a partial export directory.
    import docx
    blocks=build_sections(data,report)
    out.mkdir(parents=True)
    (out/'分页生图提示词.md').write_text(markdown(blocks))
    (out/'project.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    word(blocks,out/'分页生图提示词.docx')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('project'); p.add_argument('--output-dir',required=True); a=p.parse_args()
    try: print(json.dumps(export(json.loads(Path(a.project).read_text()),a.output_dir),ensure_ascii=False,indent=2))
    except (ValueError,FileExistsError,ImportError,KeyError,TypeError) as e: p.exit(1,str(e)+'\n')

if __name__=='__main__': main()
