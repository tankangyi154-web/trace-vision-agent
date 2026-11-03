"""Create a private, offline review form. Never auto-sign AI results as human."""
import argparse
import base64
import hashlib
import json
from pathlib import Path


def embedded_image(path):
    path=Path(path);content=path.read_bytes()
    if not 0<len(content)<=2_000_000:raise ValueError('Review image exceeds limit')
    mime='image/jpeg' if content.startswith(b'\xff\xd8\xff') else 'image/png' if content.startswith(b'\x89PNG\r\n\x1a\n') else None
    if mime is None:raise ValueError('Only actual JPEG/PNG review evidence is allowed')
    return hashlib.sha256(content).hexdigest(),'data:'+mime+';base64,'+base64.b64encode(content).decode('ascii')


def make_packet(cases,test_mode=False):
    images={};public=[]
    for case in cases:
        row={k:case.get(k) for k in ('id','title','question','answer','source_sha256','source_note')}
        row['images']=[]
        for path in case.get('image_paths',[]):
            key,data=embedded_image(path);images[key]=data;row['images'].append(key)
        public.append(row)
    data={'cases':public,'images':images,'test_mode':test_mode,
        'catalog_sha256':hashlib.sha256(json.dumps([{k:v for k,v in c.items() if k!='images'} for c in public],ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
    encoded=json.dumps(data,ensure_ascii=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e')
    return '''<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>视迹 Trace · 离线复核材料</title><style>
*{box-sizing:border-box}body{font:15px/1.8 system-ui,'Microsoft YaHei',sans-serif;color:#162b45;background:#f3f6fa;margin:0}main{max-width:1100px;margin:auto;padding:28px 20px}h1{font-size:25px;margin:0}h2{font-size:18px;margin:0 0 12px}.note,.meta{color:#61728a;font-size:13px}.reviewer,article{background:white;border:1px solid #dce4ef;border-radius:10px;padding:22px;margin:20px 0}label{display:block;margin:10px 0}input[type=text],select,textarea{font:inherit;border:1px solid #c8d3e3;border-radius:5px;padding:9px;max-width:100%;min-height:44px}input[type=text]{width:320px}textarea{width:100%;min-height:75px}.question,.answer{white-space:pre-wrap;overflow-wrap:anywhere}.question{background:#f2f5fa;padding:12px;border-radius:6px}.shots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:15px 0}.shots img{width:100%;height:auto;border:1px solid #e3e9f2}.ratings{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 18px}.ratings select{display:block;width:100%}button{font:inherit;border:1px solid #315dd4;background:#315dd4;color:#fff;border-radius:6px;min-height:44px;padding:9px 16px;cursor:pointer}button.secondary{background:#fff;color:#315dd4}button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:3px solid #99b5fc;outline-offset:2px}.actions{display:flex;flex-wrap:wrap;gap:12px}#status{color:#9a4f24;white-space:pre-line}.test{color:#a12626;font-weight:bold}@media(max-width:650px){.shots,.ratings{grid-template-columns:1fr}main{padding:20px 12px}article,.reviewer{padding:16px}}
</style><main><h1>视迹 Trace · 离线复核材料</h1>
<p class="note">查看问题、原始回答和截图，再逐项判断。图片已保存在此文件内；页面不联网、不上传评分。所有选项初始为空。</p>
<p class="note">AI复核结果与真人评审分开；这份材料不代表已经完成人工评审。只看一两张截图不能证明整段轨迹或真实身份。</p>
<div id="test-banner" class="test"></div><section class="reviewer"><label>审阅者代号<input id="reviewer" type="text" maxlength="80" autocomplete="off"></label>
<label><input id="attest" type="checkbox"> 我是真人，已亲自核对材料，且未参与本轮回答生成或代码修复。</label>
<p class="note">这是填写者声明，软件不能证明其真实身份。未勾选或未评完时只能保存草稿，不能导出为已完成独立评审。</p>
<div class="actions"><button id="draft" class="secondary">保存未完成草稿</button><button id="complete">导出已完成评审</button></div><p id="status" role="status"></p></section><div id="cases"></div>
<p class="note">通过：未发现该项问题；不通过：发现问题；不适用：该项确实不涉及。问题覆盖和事实核对不可跳过。</p>
</main><script id="data" type="application/json">'''+encoded+'''</script><script>
const packet=JSON.parse(document.getElementById('data').textContent);
const dimensions={question_coverage:'是否回答了全部所问内容',fact_accuracy:'事实或数字是否与证据相符',citation_alignment:'截图是否对应当前编号及结论',unnecessary_refusal:'依据充分的内容是否正常回答',unsupported_inference:'结论是否有画面或记录支持'};
if(packet.test_mode)document.getElementById('test-banner').textContent='自动化测试夹具，不是人工评审结果';
const host=document.getElementById('cases');
for(const [index,c] of packet.cases.entries()){
 const article=document.createElement('article');article.dataset.case=c.id;
 const heading=document.createElement('h2');heading.textContent=(index+1)+' / '+(c.title||c.id);article.append(heading);
 const q=document.createElement('p');q.className='question';q.textContent=c.question;article.append(q);
 const answer=document.createElement('p');answer.className='answer';answer.textContent=c.answer;article.append(answer);
 if(c.source_note){const n=document.createElement('p');n.className='meta';n.textContent=c.source_note;article.append(n)}
 const shots=document.createElement('div');shots.className='shots';for(const key of c.images){const image=document.createElement('img');image.src=packet.images[key];image.alt='本次回答引用的实际画面';image.loading='lazy';shots.append(image)}article.append(shots);
 const ratings=document.createElement('div');ratings.className='ratings';for(const [key,title] of Object.entries(dimensions)){
  const label=document.createElement('label');label.textContent=title;const select=document.createElement('select');select.dataset.dimension=key;
  for(const [value,text] of [['','尚未核对'],['pass','通过'],['fail','不通过'],...(['question_coverage','fact_accuracy'].includes(key)?[]:[['not_applicable','不适用']])]){const o=document.createElement('option');o.value=value;o.textContent=text;select.append(o)}label.append(select);ratings.append(label)
 }article.append(ratings);const label=document.createElement('label');label.textContent='判断依据或待改进处';const comment=document.createElement('textarea');comment.dataset.comment='1';label.append(comment);article.append(label);host.append(article)
}
function exportReview(complete){
 const status=document.getElementById('status'),name=document.getElementById('reviewer').value.trim(),attested=document.getElementById('attest').checked;
 const rows=packet.cases.map(c=>{const article=[...host.children].find(a=>a.dataset.case===c.id);const ratings={};for(const s of article.querySelectorAll('select'))ratings[s.dataset.dimension]=s.value||null;return {id:c.id,question:c.question,answer:c.answer,source_sha256:c.source_sha256,ratings,comment:article.querySelector('textarea').value}});
 if(complete&&(!name||!attested||rows.some(c=>Object.values(c.ratings).some(v=>v===null)))){status.textContent='请完成全部核对、填写审阅者代号并确认真人独立审阅；也可以先保存草稿。';return}
 const genuine=complete&&attested&&!packet.test_mode;
 const record={schema:'trace-independent-review-v1',catalog_sha256:packet.catalog_sha256,reviewer:{id:name,kind:packet.test_mode?'test_fixture':genuine?'human':'pending',independent:genuine},cases:rows};
 const blob=new Blob([JSON.stringify(record,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=packet.test_mode?'TEST-ONLY-not-human.json':complete?'Trace-human-review.json':'Trace-review-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),500);status.textContent=complete?'已导出记录；导出本身不代表评审通过。':'已保存草稿，未记为完成人工评审。';
}
document.getElementById('draft').addEventListener('click',()=>exportReview(false));document.getElementById('complete').addEventListener('click',()=>exportReview(true));
</script></html>'''


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();cases=json.loads(args.input.read_text(encoding='utf8'))['cases']
    args.output.write_text(make_packet(cases),encoding='utf8');print(json.dumps({'cases':len(cases),'offline':True,'human_ratings_prefilled':False}))
