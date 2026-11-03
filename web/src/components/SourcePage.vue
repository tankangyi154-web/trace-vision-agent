<script setup lang="ts">
import readme from '../../../README.md?url&no-inline'
import deliveryGuide from '../../../docs/local-delivery.md?url&no-inline'
import examplesGuide from '../../../docs/prepared-examples.md?url&no-inline'
import serverGuide from '../../../deploy/README.md?url&no-inline'
import uploadsGuide from '../../../docs/local-media.md?url&no-inline'
import recognitionGuide from '../../../docs/upload-recognition.md?url&no-inline'
import trackingGuide from '../../../docs/tracking-stability.md?url&no-inline'
import targetVisualGuide from '../../../docs/target-visual-analysis.md?url&no-inline'
import multiQuestionGuide from '../../../docs/multi-question-answering.md?url&no-inline'
import answerGuide from '../../../docs/agent-answer-implementation.md?url&no-inline'
import heightGuide from '../../../docs/height-validation.md?url&no-inline'
import aiReviewGuide from '../../../docs/ai-evidence-review.md?url&no-inline'
import questionPlanSource from '../../../api/media_plan.py?url&no-inline'
import visualEstimateSource from '../../../api/visual_estimates.py?url&no-inline'
import targetVisualSource from '../../../vision/target_frames.py?url&no-inline'
import trackingSource from '../../../vision/appearance_tracker.py?url&no-inline'
import contracts from '../../../docs/contracts.md?url&no-inline'
import deployment from '../../../docs/deployment.md?url&no-inline'
import visualReproduction from '../../../docs/vision.md?url&no-inline'
import liveValidation from '../../../docs/recruiting-validation.md?url&no-inline'
import patrolGuide from '../../../docs/patrol-workflow.md?url&no-inline'
import uploadSource from '../../../vision/analyze_media.py?url&no-inline'
import mediaToolsSource from '../../../api/media_tools.py?url&no-inline'
import agentSource from '../../../api/agent.py?url&no-inline'
import eventSource from '../../../api/domain.py?url&no-inline'

const sourceFiles = [
  { path: 'api/media_plan.py', description: '多问题清单、当前编号与同素材追问范围校验', url: questionPlanSource },
  { path: 'api/visual_estimates.py', description: '带参照的目测范围与非测量结果校验', url: visualEstimateSource },
  { path: 'vision/target_frames.py', description: '按编号选择实际画面、质量评估与局部放大', url: targetVisualSource },
  { path: 'vision/appearance_tracker.py', description: '行人交叠后的外观核对与有歧义时中断关联', url: trackingSource },
  { path: 'vision/analyze_media.py', description: '上传素材的检测、跟踪与补充识别', url: uploadSource },
  { path: 'api/media_tools.py', description: '数量、出现时刻和截图的查询与绑定', url: mediaToolsSource },
  { path: 'api/agent.py', description: '工具调用编排、执行预算与回答校验', url: agentSource },
  { path: 'api/domain.py', description: '历史区域案例中的事件与观测驻留计算', url: eventSource },
]
const documents = [
  { name: 'local-delivery.md', description: '离线案例、CPU便携版、真实耗时与环境边界', url: deliveryGuide },
  { name: 'prepared-examples.md', description: '三个新视频的真实结果、来源许可与证据核对', url: examplesGuide },
  { name: 'deploy/README.md', description: '案例服务与私有分析的部署文件；尚未上线', url: serverGuide },
  { name: 'ai-evidence-review.md', description: 'AI逐项证据复核、修复内容与仍存限制', url: aiReviewGuide },
  { name: 'height-validation.md', description: '公开身高样本、真实误差、失败案例与适用范围', url: heightGuide },
  { name: 'agent-answer-implementation.md', description: '简洁回答、按问题取证、本机复用与真实验证范围', url: answerGuide },
  { name: 'multi-question-answering.md', description: '分类时长比较与指定编号外观的完整回答', url: multiQuestionGuide },
  { name: 'target-visual-analysis.md', description: '真正看图分析、质量限制、隐私与实际验证', url: targetVisualGuide },
  { name: 'tracking-stability.md', description: '遮挡串号的修复方式、模型来源与验证范围', url: trackingGuide },
  { name: 'upload-recognition.md', description: '类型配色、低清识别改进与汽车抽检范围', url: recognitionGuide },
  { name: 'patrol-workflow.md', description: '巡查复核、人工记录、离线证据单与当前适用范围', url: patrolGuide },
  { name: 'recruiting-validation.md', description: '本轮真实模型调用、视觉链路与验证范围', url: liveValidation },
  { name: 'README.md', description: '本地启动、依赖、问答配置与实现索引', url: readme },
  { name: 'local-media.md', description: '当前上传流程、补查、临时文件与使用边界', url: uploadsGuide },
  { name: 'contracts.md', description: '场景、事件与工具的数据约定', url: contracts },
  { name: 'vision.md', description: '历史公开视频案例的视觉复现与抽检方法', url: visualReproduction },
  { name: 'deployment.md', description: '公开部署的准备说明，当前未公开部署', url: deployment },
]
</script>

<template>
  <article class="source-guide">
    <a class="source-back" href="#implementation">返回实现摘要</a>
    <h1>源码与复现</h1>
    <p class="source-intro">以下文件来自当前版本，可点击下载核对。<a href="https://github.com/tankangyi154-web/trace-vision-agent" target="_blank" rel="noopener noreferrer">在 GitHub 查看完整源码</a></p>
    <section aria-labelledby="source-code-title">
      <h2 id="source-code-title">关键源码</h2>
      <ul><li v-for="file in sourceFiles" :key="file.path"><a :href="file.url" :download="file.path.split('/').at(-1)">{{ file.path }}</a><span>{{ file.description }}</span></li></ul>
    </section>
    <section aria-labelledby="source-docs-title">
      <h2 id="source-docs-title">运行与详细说明</h2>
      <ul><li v-for="doc in documents" :key="doc.name"><a :href="doc.url" :download="doc.name">{{ doc.name }}</a><span>{{ doc.description }}</span></li></ul>
      <p><a href="/api/docs" target="_blank" rel="noopener noreferrer">查看API参数</a></p>
    </section>
  </article>
</template>

<style scoped>
.source-guide{width:min(850px,calc(100% - 80px));margin:30px auto 44px;color:var(--ink)}
.source-back{display:inline-flex;align-items:center;min-height:44px;font-size:13px}
h1{font-size:26px;font-weight:600;line-height:1.5;margin:12px 0}
.source-intro{font-size:14px;line-height:1.9;color:var(--muted)}
section{border-top:1px solid var(--line);padding-top:22px;margin-top:24px}
h2{font-size:17px;font-weight:600;margin:0 0 13px}
ul{list-style:none;margin:0;padding:0;display:grid;gap:10px}
li{font-size:13px;line-height:1.8;display:grid;grid-template-columns:235px minmax(0,1fr);gap:12px;align-items:center}
li a{min-height:44px;display:inline-flex;align-items:center;overflow-wrap:anywhere}
li span{color:var(--muted)}
section>p{font-size:13px;line-height:1.8;margin-top:16px}
section>p a{display:inline-flex;min-height:44px;align-items:center}
a{text-decoration:underline;text-underline-offset:4px}a:focus-visible{outline:3px solid #91aafd;outline-offset:4px}
@media(max-width:600px){.source-guide{width:calc(100% - 36px);margin:20px auto}h1{font-size:23px}li{grid-template-columns:1fr;gap:0}li a{font-size:13px}li span{padding-bottom:7px}}
</style>
