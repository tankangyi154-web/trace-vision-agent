from html import escape
import json
from urllib.parse import urlsplit
from api.domain import analyze

NAMES={'enter':'进入','exit':'离开','dwell':'连续驻留','initial_presence':'首次区内观测','observation_gap':'观测中断'}


def safe_url(value,origin=''):
    if value.startswith('/media/') and urlsplit(origin).scheme in ('http','https'):
        return origin.rstrip('/')+value
    return value if urlsplit(value).scheme in ('http','https') else '#'


def report(scene,zone_id,dwell_seconds,format,origin=''):
    analysis=analyze(scene,zone_id,dwell_seconds)
    if format=='json':
        return json.dumps({'report_kind':'deterministic_computation','media_base_url':origin,'scene':{k:scene[k] for k in ('id','title','source','processing','notes')},
                           'analysis':analysis},ensure_ascii=False,indent=2),'application/json'
    lines=[f"# {scene['title']} · 事件计算报告",'',
           '> 本报告由轨迹与区域规则确定性计算生成；不是大模型回答。视觉检测已预先完成。', '',
           f"区域：{zone_id}；连续驻留提示阈值：{dwell_seconds:g} 秒。",'',
           f"所选区域内标记 {analysis['summary']['tracks']} 个（全片 {analysis['summary']['clip_tracks']} 个标记）；观察到进入 {analysis['summary']['entries']} 次；驻留提示 {analysis['summary']['dwell_alerts']} 次。标记数不等于真实世界唯一物体数。",'',
           '## 可观测驻留排序','', '| 目标 | 类别 | 累计时长/秒 | 证据 |','| --- | --- | ---: | --- |']
    lines.extend(f"| {d['track_id']} | {d['label']} | {d['observed_seconds']:.3f} | {', '.join(d['evidence_ids'])} |" for d in analysis['dwell'])
    lines+=['','## 事件索引','', '| 类型 | 目标 | 开始/秒 | 结束/秒 | 证据 | 截断 |','| --- | --- | ---: | ---: | --- | --- |']
    lines.extend(f"| {NAMES[e['type']]} | {e['track_id']} | {e['start']:.3f} | {e['end']:.3f} | {', '.join(e['evidence_ids'])} | {'是' if e['censored'] else '否'} |" for e in analysis['events'])
    lines+=['','## 证据截图','']
    lines.extend(f"- {e['id']}：目标 {e['track_id']}，截图 {e['t']:.3f} 秒，[查看截图]({safe_url(e['image_url'],origin)})" for e in scene['evidence'])
    lines+=['','## 来源与限制','',f"素材：[{scene['source']['title']}]({scene['source']['url']})；作者：{scene['source']['author']}；许可：{scene['source']['license']}。",
            '只累计连续有效观测；漏检时间不计驻留。首次已在区域内不视为进入；区间截断表示真实结束未知。目标 ID 只在片段内有效，观测中断不等于证实遮挡。',
            '无真实距离标定，不能推断航速、实际距离、损伤、身份或违法。',*scene['notes']]
    text='\n'.join(lines)+'\n'
    if format=='html':
        # Safe standalone report with real links; model/source HTML is never executed.
        esc=lambda value:escape(str(value),quote=True)
        rows=''.join(f"<tr><td>{esc(NAMES[e['type']])}</td><td>{esc(e['track_id'])}</td><td>{e['start']:.3f}</td><td>{e['end']:.3f}</td><td>{esc(', '.join(e['evidence_ids']))}</td><td>{'是' if e['censored'] else '否'}</td></tr>" for e in analysis['events'])
        ranks=''.join(f"<tr><td>{esc(d['track_id'])}</td><td>{esc(d['label'])}</td><td>{d['observed_seconds']:.3f}</td></tr>" for d in analysis['dwell'])
        evidence=''.join(f"<li><a href=\"{esc(safe_url(e['image_url'],origin))}\">{esc(e['id'])}</a>：目标 {esc(e['track_id'])}，截图 {e['t']:.3f} 秒</li>" for e in scene['evidence'])
        source=scene['source']
        source_link=f"<a href=\"{esc(safe_url(source['url']))}\">{esc(source['title'])}</a>"
        notes=''.join(f'<li>{esc(note)}</li>' for note in scene['notes'])
        page=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta name="referrer" content="no-referrer"><title>事件计算报告</title><style>body{{max-width:1000px;margin:40px auto;padding:0 24px;color:#142a43;font:16px/1.7 system-ui}}table{{border-collapse:collapse;width:100%;margin:20px 0}}td,th{{text-align:left;padding:8px;border-bottom:1px solid #dce3ed;overflow-wrap:anywhere}}a{{color:#2455e6}}.table{{overflow:auto}}</style></head><body>
<h1>{esc(scene['title'])} · 事件计算报告</h1><p>本报告由轨迹与区域规则确定性计算生成；不是大模型回答。视觉检测已预先完成。</p><p>区域 {esc(zone_id)}；连续驻留阈值 {dwell_seconds:g} 秒。</p>
<h2>可观测驻留排序</h2><div class="table"><table><thead><tr><th>目标</th><th>类别</th><th>累计时长/秒</th></tr></thead><tbody>{ranks}</tbody></table></div>
<h2>事件索引</h2><div class="table"><table><thead><tr><th>类型</th><th>目标</th><th>开始/秒</th><th>结束/秒</th><th>证据</th><th>截断</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>证据截图</h2><ul>{evidence}</ul><h2>来源与限制</h2><p>素材：{source_link}；作者：{esc(source['author'])}；许可：{esc(source['license'])}。</p><p>只累计连续有效观测，漏检时间不计驻留。首次已在区域内不视为进入；截断区间是已观测时长下界。目标 ID 只在片段内有效，观测中断不等于证实遮挡。无标定视频不能推断航速、实际距离、损伤、身份或违法。</p><ul>{notes}</ul></body></html>'''
        return page,'text/html'
    return text,'text/markdown'
