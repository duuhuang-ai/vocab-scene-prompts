# 分类 分页与数据约定

## 输入与原文

`prepare_vocab.py`接受xlsx、csv、tsv、txt、json。Word资料由模型读取或用python-docx抽取表格，先保存下列JSON输入；复杂合并表头或无结构文字也先人工判断映射。

JSON输入为数组，可为字符串单词，或对象：

```json
[
  {"serial": 1, "word": "bread", "phonetic": "/bred/", "meaning": "n. 面包"},
  "soup"
]
```

对象键可使用`序号/单词/音标/释义`等常见中英文表头。未知表头用`--word-column`、`--phonetic-column`、`--meaning-column`、`--serial-column`指定。xlsx多工作表须明确`--sheet`。CSV/TSV默认首行为表头；TXT按非空行逐词输入，不拆解词组。

快照保留所有已读取单元格、空行、附加列与来源文件SHA256。含非空数据但单词为空时拒绝准备，而非静默丢行。Excel公式保留在快照，教学列出现公式时要求提供可读值，不运行公式或宏。中英文字符串不去空格、不统一大小写、不纠错；处理建议另列。

稳定编号与来源行关联；一个项目中不因排序改变编号。原字段保留为`source_entries[].original`。原文件缺少的字段写null；经外部核对的补充放`supplements`，保留资料来源和核对状态。补充仅填缺项，不覆盖非空原字段；原文疑似错误时标记待复核并说明，不在本流程自动订正。

## 分类与分页

- 先保存项目分类规则，再分类。一条记录有且只有一个主主题；原释义可多义，主类依据明确的选用义项。无法确定的记录归待复核主题，selected_meaning可为null。
- 主题不能由拼写相近决定。主题数量随词表变化；单页分组基于生活场景和情节，不能把整个大主题直接塞一页。
- 默认每页8—12词，长音标、长释义或复杂动作可减少；必要时在composition_notes说明超出范围原因。8—12是建议，不是硬性Schema限制。
- 同一记录默认只首次教学一次。复习重用需teaching_role=review、理由非空且晚于首次教学页；重复拼写的不同来源记录仍分别处理。
- 同页可以一个主场景或多个连续场景。relative_height按全页高度计，总和可小于1，为标题和留白留空间。
- 先写清人物、动作、可辨物品、标签位置与视觉目标，再合成提示词。不要依靠风格词代替场景设计。情节与本场景义项一致，形容词与抽象词可用context而非物体命名箭头。

## 字段关系

`project`标明sample或full范围，`style_profile`保存本项目完整风格。`classifications`逐条引用source_entries与themes。`pages[].vocabulary`引用来源记录，并保存最终上画词条；`pages[].layout`分配本页词汇与人物。`pages[].prompt.ready_to_copy`是实际可独立使用的指令。

缺项补充结构：`entry_id, phonetic, meaning, part_of_speech, evidence, verification_status`。未填写的补充字段为null，evidence为实际核对的词典链接或可定位资料名称，不编造引用。verification_status为verified或pending_review。只有verified补充可用于prompt_ready页。

ready表示该记录可用于规划；pending_review表示仍有疑点；prompt_ready表示页面文稿就绪。未生成图片时不使用图片验收状态。

## 校验与导出

先完成语义规划，再编译，再校验，再导出。编译器会计算coverage，拒绝把不完整词条编成就绪页。允许导出部分成果，但显式列出全部待复核与未分页来源编号，不输出未就绪页为生图指令。

校验器实现随包Schema所用关键字的结构校验与额外关系检查，遇到未知关键字会失败；它不是通用JSON Schema引擎。发布包时用标准Draft2020-12验证器另外检查Schema与示例。语义判断仍由模型负责；字段和覆盖率通过不等于分类正确或画面准确。

每页完整提示词均展开文字、场景、指向、风格与负面词。Word导出为可编辑段落与表格；渲染验证留在work，不加入安装包。发现字体问题使用当前任务目录的临时字体配置，不修改系统配置。目录已存在时换新版本目录，不删除或覆盖。
