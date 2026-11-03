<script setup lang="ts">
import Icon from './Icon.vue'
import RecordedRuns from './RecordedRuns.vue'
</script>
<template>
  <article class="implementation-summary">
    <header><div><p class="eyebrow">实现与取舍</p><h1>从视觉观测，到可核查的回答。</h1></div></header>
    <p class="purpose">模型组织查询与解释；数量、时间与证据引用由程序核对。</p>
    <div class="architecture" aria-label="系统架构"><span>素材 / 公开案例</span><Icon name="arrow" :size="16" /><span>独立视觉 Worker</span><Icon name="arrow" :size="16" /><span>结构化观测与工具</span><Icon name="arrow" :size="16" /><span>有界 Agent</span><Icon name="arrow" :size="16" /><span>引用核验与回看</span></div>
    <section><h2>本项目实现的部分</h2><dl class="contributions"><div><dt>媒体任务</dt><dd>私有上传、指定类别检测、视频跟踪与同素材补查；API 与 CPU 视觉 Worker 分离。</dd></div><div><dt>确定性事实</dt><dd>区分初始存在与进入、累计观测与连续区间、跟踪记录与唯一物体，保留缺口与关联未决。</dd></div><div><dt>Agent 执行</dt><dd>LangGraph 编排工具，每次最多三次模型调用、五次工具执行，校验本轮取回的引用与声明。</dd></div><div><dt>工程约束</dt><dd>会话隔离、请求幂等、额度控制、临时数据清理、自动化测试与脱敏运行记录。</dd></div></dl></section>
    <section><h2>三个关键取舍</h2><ol><li><strong>事实由工具计算。</strong>模型选择查询并解释，程序核对数值与引用。</li><li><strong>检测到，不等于身份已确认。</strong>轨迹关联、遮挡和缺帧都会限制结论。</li><li><strong>视觉处理独立于 API。</strong>耗时任务在受控子进程中运行。</li></ol></section>
    <RecordedRuns />
    <nav class="implementation-links" aria-label="核对实现"><a href="#source">源码与复现 <Icon name="arrow" :size="15" /></a><a href="#evaluation">视觉开发抽检 <Icon name="arrow" :size="15" /></a><a href="#investigation">船舶缺口专项复核 <Icon name="arrow" :size="15" /></a></nav>
  </article>
</template>
<style scoped>
.implementation-summary{width:min(1000px,calc(100% - 80px));margin:45px auto;color:var(--ink)}header{display:flex;justify-content:space-between;align-items:center;gap:20px}.eyebrow{font-size:11px;letter-spacing:.12em;color:var(--muted);margin:0 0 12px}h1{font-size:30px;line-height:1.5;font-weight:600;margin:0}.purpose{font-size:16px;line-height:1.9;color:#5d6b80;margin:20px 0 24px}.architecture{display:flex;align-items:center;justify-content:space-between;gap:12px;background:#f3f6fc;border:1px solid #e0e7f2;border-radius:8px;padding:23px 20px;font-size:12px;line-height:1.8;color:#455d84}.architecture>svg{flex-shrink:0}section{margin-top:34px}h2{font-size:19px;font-weight:600;margin:0 0 20px}.contributions{display:grid;grid-template-columns:1fr 1fr;gap:23px 35px;margin:0}.contributions dt{font-size:14px;font-weight:600;margin-bottom:7px}.contributions dd{font-size:13px;line-height:1.9;color:#66748a;margin:0}ol{margin:0;padding-left:22px;font-size:13px;line-height:2;color:#66748a}li{margin-bottom:10px}li strong{font-weight:550;color:#32445f}.implementation-links{display:flex;gap:25px;flex-wrap:wrap;border-top:1px solid #e1e7ef;padding-top:20px;margin-top:30px}.implementation-links a{display:inline-flex;align-items:center;gap:7px;min-height:44px;font-size:12px;text-underline-offset:4px}.note{color:var(--muted);font-size:11px;line-height:1.9;margin:9px 0 0}a:focus-visible{outline:3px solid #91aafd;outline-offset:4px}@media(max-width:650px){.implementation-summary{width:calc(100% - 36px);margin:28px auto}header{align-items:start;flex-direction:column;gap:9px}h1{font-size:25px}.purpose{font-size:14px}.architecture{flex-wrap:wrap;justify-content:flex-start;gap:10px;padding:17px}.contributions{grid-template-columns:1fr;gap:19px}.contributions dd,ol{font-size:14px}.implementation-links{gap:15px}.note{font-size:12px}section{margin-top:28px}}
</style>
