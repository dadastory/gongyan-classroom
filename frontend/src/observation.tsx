import { useEffect, useState } from 'react';
import { Button, Card, Space, Table, Tag, Tooltip } from 'antd';
import { Link } from 'react-router-dom';
import { Countdown } from './components';
import { RULE_MODE_NAMES, RULE_NAMES, SUPPORT_NAMES, timeText } from './constants';
import type { AnalysisTask, AssistantOverview, GroupDetail } from './types';

const statusColor = (status: string) => status === 'failed' || status.startsWith('model-') ? 'warning'
  : ['generating', 'analyzing', 'queued'].includes(status) ? 'processing'
  : status === 'needs-teacher' ? 'gold' : 'default';

export function SupportTag({ assistant }: { assistant: Pick<AssistantOverview, 'status' | 'cooldown_until' | 'rules_enabled'> }) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now() / 1000), 1000); return () => clearInterval(timer); }, []);
  const status = assistant.status === 'cooldown' && (assistant.cooldown_until || 0) <= now
    ? assistant.rules_enabled ? 'monitoring' : 'manual' : assistant.status;
  return <Tag color={statusColor(status)} bordered={false}>{SUPPORT_NAMES[status] || status}</Tag>;
}

export function AssistantPanel({ group }: { group: GroupDetail }) {
  const state = group.assistant;
  if (!state) return null;
  return <Card size="small" className="assistant-panel" title={<Space><span>实时助教状态</span><SupportTag assistant={state} /></Space>}
    extra={<span className="muted small">更新 {new Date(state.updated_at * 1000).toLocaleTimeString('zh-CN', { hour12: false })}</span>}>
    <div className="assistant-status-grid">
      <div><span>教育支架规则</span><strong>{state.rules_enabled ? RULE_MODE_NAMES[state.mode] : '未启用 · 可手动总结'}</strong><small>观察窗口 {state.window_seconds} 秒</small></div>
      <div><span>投入编码任务</span><strong>排队 {state.analysis_pending} · 运行 {state.analysis_running}</strong><small>待配置 {state.analysis_blocked} · 失败 {state.analysis_failed}{state.retrying > 0 && ` · 自动重试 ${state.retrying}`}</small></div>
      <div><span>教育支架进度</span><strong>生成 {state.generating} · 待确认 {state.pending_approval}</strong><small>仅提醒 {state.notifications} · 已发布 {state.published} · 失败 {state.generation_failed}</small></div>
      <div><span>冷却与复查</span><strong>{state.cooldown_until ? <Countdown deadline={state.cooldown_until} /> : '当前无冷却'}</strong><small>{state.review_waiting_data ? `${state.review_waiting_data} 条提示等待更多观察数据` : state.next_review_at ? <>下次复查 <Countdown deadline={state.next_review_at} /></> : '暂无待复查提示'}</small></div>
    </div>
    <div className="assistant-concerns" aria-label="当前关注点">
      <span className="muted">当前关注点</span>
      {group.concerns?.length ? group.concerns.map((item, index) => <Tooltip key={`${item.rule}-${index}`} title={item.reason}><Tag color="warning">{RULE_NAMES[item.rule] || item.rule}</Tag></Tooltip>)
        : <span className="muted">{group.metrics?.pending_messages || group.metrics?.failed_messages ? '分析未完成，暂不判断' : group.metrics?.total_messages ? '暂未观察到持续关注点' : '暂无讨论数据'}</span>}
      {state.pending_approval + state.notifications > 0 && <span className="muted">请在下方“智能提示”中处理</span>}
    </div>
    <div className="assistant-model muted small">{state.model_status === 'ready' ? `当前模型 ${state.model} · 连接 v${state.connection_version}` : state.model_status === 'disabled' ? '模型未启用，讨论消息仍正常保存。' : '尚未配置模型，讨论消息仍正常保存。'}
      {state.model_status !== 'ready' && <Link to="/settings"><Button type="link" size="small">配置模型</Button></Link>}
    </div>
  </Card>;
}

export function AnalysisTasks({ group }: { group: GroupDetail }) {
  return <Card><Table<AnalysisTask> rowKey="id" dataSource={group.jobs || []} scroll={{ x: 900 }} pagination={{ pageSize: 8 }} columns={[
    { title: '任务 / 阶段', render: (_, task) => <>{task.kind === 'analysis' ? '投入编码' : '提示生成'}<br /><Tag>{task.phase_id === group.phase_id ? '当前阶段' : '此前阶段'}</Tag></> },
    { title: '状态', render: (_, task) => <><Tag color={task.status === 'running' ? 'processing' : task.status === 'failed' ? 'warning' : 'default'}>{{ pending: task.error ? '自动重试排队' : '待执行', running: '执行中', blocked: '待配置模型', complete: '已完成', failed: '失败', stale: '已过期' }[task.status] || task.status}</Tag>{task.status === 'pending' && <div className="muted small">执行等待 <Countdown deadline={task.available_at} /></div>}</> },
    { title: '尝试次数', dataIndex: 'attempts' },
    { title: '运行版本', render: (_, task) => task.skill_slug ? <div className="task-version"><span>{task.skill_slug} {task.skill_version == null ? '版本未记录' : `v${task.skill_version}`}</span><small>{task.model || '模型未记录'} · 连接 {task.connection_version == null ? '未记录' : `v${task.connection_version}`} · 课题 {task.config_version == null ? '未记录' : `v${task.config_version}`}</small></div> : <span className="muted">开始执行时记录</span> },
    { title: '创建 / 说明', render: (_, task) => <><span className="muted small">{timeText(task.created_at)}</span>{task.error && <div className="small">{task.error}</div>}</> },
  ]} /></Card>;
}
