"""Expand every ready page into a self-contained image-generation prompt."""
import argparse
import json
from pathlib import Path
from validate_project import validate, calculate_coverage

def compile_project(data):
    data['coverage']=calculate_coverage(data)
    validate(data,check_prompts=False)
    cfg=data['project']['defaults']; style=data['style_profile']
    for p in data['pages']:
        if p['status']!='prompt_ready': continue
        labels='\n'.join(f"{v['display_word']} | {v['display_phonetic']} | {v['display_part_of_speech']} {v['display_meaning']}" for v in p['vocabulary'])
        actors='\n'.join(c['id']+'：'+c['description'] for c in p['characters'])
        scenes='\n'.join(f"{s['order']}. 全页高度约{s['relative_height']*100:g}%：{s['scene_description']}" for s in sorted(p['layout'],key=lambda s:s['order']))
        links='\n'.join(f"{v['display_word']}：位置为{v['label_position']}；" + (f"箭头准确落在{v['visual_target']}。" if v['link_mode']=='arrow' else f"用情境表达{v['visual_target']}，不用物品命名箭头。") for v in p['vocabulary'])
        prompt=f'''请生成一张{cfg['aspect_ratio']}的英语场景词汇漫画，建议{cfg['width']}×{cfg['height']}像素。一页对应一张图片。

【上画主标题】
{p['title']}

【上画副标题】
{p['subtitle']}

【准确教学文字】
共{len(p['vocabulary'])}个词条。以下每条用竖线分隔的三部分，在画面中固定排为三行：英文、音标、词性与中文。逐字采用，不添加其他义项。
{labels}

【场景与故事】
{p['scene_setting']}
{p['story']}

【人物设定】
{actors}

【画面布局】
{p['composition_notes']}
{scenes}

【标签位置与指向】
{links}

【统一视觉风格】
{style['positive_prompt']}

【负面提示词】
{style['negative_prompt']}

【生成后核对要求 不作为画面文字】
'''+'\n'.join(p['qa_checks'])
        p['prompt']={'ready_to_copy':prompt,'negative_prompt':style['negative_prompt']}
    validate(data)
    return data

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project'); parser.add_argument('--output',required=True); args=parser.parse_args()
    target=Path(args.output)
    if target.exists(): parser.exit(1,'Output exists; use a new filename\n')
    try:
        data=compile_project(json.loads(Path(args.project).read_text()))
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        print(target)
    except (ValueError,KeyError,TypeError) as e: parser.exit(1,str(e)+'\n')

if __name__=='__main__': main()
