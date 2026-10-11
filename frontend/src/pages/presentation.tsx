import { useEffect, useState } from 'react';
import { Button, Space, Tag } from 'antd';
import { FullscreenOutlined, FullscreenExitOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { Link, useParams } from 'react-router-dom';
import { useResource, useTopicLive } from '../api';
import { Countdown, ErrorNotice, LiveTag, Metric, PageLoad, StateTag } from '../components';
import { COGNITIVE_NAMES, SUPPORT_NAMES } from '../constants';
import type { Presentation } from '../types';

export function PresentationPage() {
  const { topicId } = useParams();
  const resource = useResource<Presentation>(`/topics/${topicId}/presentation`);
  const connected = useTopicLive(topicId, resource.refresh);
  const [now, setNow] = useState(new Date());
  const [fullscreen, setFullscreen] = useState(Boolean(document.fullscreenElement));
  useEffect(() => { const timer = setInterval(() => setNow(new Date()), 1000); const listener = () => setFullscreen(Boolean(document.fullscreenElement)); document.addEventListener('fullscreenchange', listener); return () => { clearInterval(timer); document.removeEventListener('fullscreenchange', listener); }; }, []);
  if (!resource.data) return <PageLoad error={resource.error} retry={resource.refresh} />;
  const topic = resource.data;
  const ns = topic.groups.reduce((sum, group) => sum + group.metrics.NS, 0);
  const na = topic.groups.reduce((sum, group) => sum + group.metrics.NA, 0);
  const online = topic.groups.reduce((sum, group) => sum + group.online_count, 0);
  return <div className="presentation-page"><header className="presentation-header"><div><span className="eyebrow">共研 / LIVE CLASSROOM</span><h1>{topic.title}</h1><Space><LiveTag connected={connected} /><span className="muted">匿名小组展示 · 当前观察窗口</span></Space></div><div className="presentation-clock"><strong>{now.toLocaleTimeString('zh-CN', { hour12: false })}</strong><Space><Link to={`/topics/${topicId}`}><Button ghost size="small" icon={<ArrowLeftOutlined />}>返回工作台</Button></Link><Button ghost size="small" icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} onClick={() => { if (document.fullscreenElement) void document.exitFullscreen(); else void document.documentElement.requestFullscreen().catch(() => undefined); }}>{fullscreen ? '退出全屏' : '全屏'}</Button></Space></div></header>
    <ErrorNotice error={resource.error} retry={resource.refresh} />
    <div className="presentation-summary"><Metric label="有效参与" value={na} suffix={`/ ${topic.student_count}`} /><Metric label="有效讨论消息" value={ns} /><Metric label="当前在线" value={online} suffix="人" /><Metric label="阶段成果" value={topic.groups.filter(g => g.metrics.TC).length} suffix={`/ ${topic.groups.length} 组`} /></div>
    <div className="presentation-groups">{topic.groups.map((group, index) => { const codes = group.metrics.cognitive; const total = Object.values(codes).reduce((a, b) => a + b, 0); return <section className="presentation-group" key={index}>
      <div className="presentation-group-title"><h2><span>{String(index + 1).padStart(2, '0')}</span>{group.name}</h2><StateTag state={group.state} /></div>
      <div className="presentation-phase"><span>{group.state === 'waiting' ? '等待开始' : topic.stages[group.phase_index]?.name}</span><Countdown deadline={group.deadline} /></div>
      <div className="presentation-group-metrics"><div><span>有效参与</span><strong>{group.metrics.NA}<small>/{group.metrics.member_count}</small></strong></div><div><span>有效消息</span><strong>{group.metrics.NS}</strong></div><div><span>在线</span><strong>{group.online_count}</strong></div></div>
      <div className="cognitive-stack">{total ? Object.entries(codes).map(([code, count], i) => count > 0 && <span title={`${code} ${COGNITIVE_NAMES[i]}：${count}`} key={code} style={{ flex: count, background: ['#687d9b', '#7c9dcc', '#62a3af', '#8bc0a7', '#c1cf8c', '#d7b57e'][i] }} />) : <span className="no-coding">等待讨论与分析</span>}</div>
      <div className="presentation-group-bottom"><span>分析覆盖 {group.metrics.coverage == null ? '暂无' : `${Math.round(group.metrics.coverage * 100)}%`}</span><Tag color={group.metrics.TC ? 'success' : 'default'} bordered={false}>{group.metrics.TC ? '成果已提交' : '成果待提交'}</Tag></div>
      <div className="presentation-support"><span>{group.metrics.failed_messages ? `分析失败 ${group.metrics.failed_messages} 条` : group.metrics.pending_messages ? `待分析 ${group.metrics.pending_messages} 条` : group.metrics.total_messages ? '编码已完成' : '等待讨论数据'}</span><span>助教 · {SUPPORT_NAMES[group.support_status] || '持续观察中'}{group.pending_prompts > 0 && ` (${group.pending_prompts})`}</span></div>
    </section>; })}</div>
    {!topic.groups.length && <div className="presentation-empty">课堂准备中，等待老师完成分组。</div>}
    <footer className="presentation-footer"><span>一起探索 · 一起建构</span><div>{COGNITIVE_NAMES.map((name, i) => <span key={i}><i style={{ background: ['#687d9b', '#7c9dcc', '#62a3af', '#8bc0a7', '#c1cf8c', '#d7b57e'][i] }} />C{i} {name}</span>)}</div><span>共研 · 课堂协作学习</span></footer>
  </div>;
}
