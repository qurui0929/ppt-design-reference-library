# 原生输入协议 v1

作者器输入 `deck.json`：

```json
{
  "schema_version": 1,
  "design": {
    "font": "Microsoft YaHei",
    "palette": {"ink":"#122A43","accent":"#147D92","secondary":"#DF8C41","muted":"#526878","light":"#EDF5F6","white":"#FFFFFF","rule":"#CFDEE4"}
  },
  "slides": [{
    "id":"page-01", "layout":"N03", "title":"项目实施流程",
    "slots": {"lead":"原始说明文字","step1_title":"第一步","step1_body":"源材料内容"},
    "sources": [], "allow_missing_slots": false
  }]
}
```

先下载所选 recipe，读取其 elements 里的 `bind`，再创建 `slots`。所有文字槽位均有名称，缺失时默认报错；额外槽位也报错，防止内容静默丢失。标题独立输入。不能将完整段落强行映射到单词槽位。每个 `bind` 的 `max_chars` 是初始容量；引擎超限报错后应更换或调整配方，不自动缩字、截断。

`recipe_overrides` 可指向相对 spec 的本地 JSON，复制参考配方后修改几何/字号/增加槽位；记录修改原因。配方中的预设文本只能是结构标签，事实内容必须绑定。所有坐标都是 `[x,y,w,h]`，相对 1280×720 归一化；字体 CSS px，颜色按 palette token。元素支持：`text`、`shape`、`line`、`table`、`chart`、`image`。结构形状可用 rect、ellipse、rightArrow 等原生形状；它们用于说明关系，不用于画装饰插图。

表格数据通过 `slide.tables[bind]` 提供二维数组；图表通过 `slide.charts[bind]` 提供 `type/categories/series`，不能将示例值当真实值。图像通过 `slide.images[bind]` 指定本地文件、mime 与来源；照片保持比例，裁剪前核实主体。可编辑表格与图表由原生对象创建。

作者器导出 `deck.pptx`、`rendered/slide-NN.png`、`build-report.json`。这是待最终验证的草稿，不可仅据此承诺所有图表数据编辑功能。如果宿主渲染失败，保留实际错误并使用可用 Office/LibreOffice 导出检查；不能拿另一份文件的渲染当当前文件的验收。正式交付还须使用宿主 Presentations 最终验证器；便携脚本 QA 不是它的替代品。

新建的定量图表必须包含标题，并保留原生可编辑数据工作簿。Artifact Tool 的 literal series 导出可能只有图表缓存；若数据确实是本任务提供的完整字面值，可在最终验证时明确使用 `materializeLiteralChartWorkbooks: true`，由宿主生成对应的 Excel 数据快照并验证关联。它不是原始公式的恢复；现有源工作簿与公式须原样保留。设置 `requiredNativeChartOwnerSlides`、`requiredNativeTableOwnerSlides`、实际页数和字体策略，保留验证回执，并渲染最终文件。

## 验证

`qa_deck.py` 检查 ZIP 完整性、幻灯片顺序、原生文本覆盖、图片/图表/表格对象数、越界、近整页图片和字体；文字在普通文本框内重叠的情况也报告。背景容器和故意的节点包含文字不按文本重叠处理。图表/表格单元格文字另有原生数据验证，文本覆盖检查只核对字符串槽位和标题。程序不能可靠检测所有中文实际排版溢出，必须看实际渲染。

检查所有最终页，而不是只看总览。不要在幻灯片里写 QA 说明、版式编号、下载来源；这些在项目记录或讲者备注中。
