import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import type { ComponentRef } from 'react';
import { App, Alert, Avatar, Button, Card, Collapse, Drawer, Form, Input, Select, Space, Switch, Table, Tabs, Tag, Tooltip } from 'antd';
import { Bubble, Sender } from '@ant-design/x';
import { ArrowLeftOutlined, PlayCircleOutlined, PauseCircleOutlined, ForwardOutlined, FileTextOutlined, RobotOutlined, CommentOutlined, CloseOutlined } from '@ant-design/icons';
import { Link, useParams } from 'react-router-dom';
import type { EChartsOption } from 'echarts';
import { api, send, useResource, useTopicLive, errorMessage, newClientId } from '../api';
import { useDiscussionMessages } from '../discussion';
import { useAuth } from '../auth';
import { StableModal } from '../stable-modal';
import { AnalysisTasks, AssistantPanel } from '../observation';
import { Chart, Countdown, EmptyState, ErrorNotice, LiveTag, Metric, PageLoad, SectionTitle, StageTrack, StateTag } from '../components';
import { COGNITIVE_NAMES, durationText, EMOTION_NAMES, INTERVENTION_NAMES, METACOGNITIVE_NAMES, RULE_MODE_NAMES, RULE_NAMES, SOCIAL_NAMES, timeText } from '../constants';
import type { ChatMessage, Group, GroupDetail, Intervention, MeaningUnit, Metrics, StudentMetrics } from '../types';

export function InterventionList({ items, refresh, groups = [] }: { items: Intervention[]; refresh: () => Promise<unknown>; groups?: Group[] }) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState<string>();
  const act = async (item: Intervention, action: string) => {
    setBusy(item.id);
    try { await send(`/interventions/${item.id}/${action}`); await refresh(); }
    catch (error) { void message.error(errorMessage(error)); } finally { setBusy(undefined); }
  };
  return items.length ? <div className="intervention-list">{items.map(item => <Card key={item.id} size="small">
    <div className="intervention-heading"><Space><RobotOutlined /><strong>{RULE_NAMES[item.rule] || item.rule}</strong><Tag color={item.status === 'pending' ? 'warning' : item.status === 'published' ? 'success' : 'default'}>{INTERVENTION_NAMES[item.status] || item.status}</Tag></Space><span className="muted">{timeText(item.created_at)}</span></div>
    <p className="preserve-text">{item.content || (item.status === 'generating' ? '正在生成提示…' : item.evidence.reason)}</p>
    <div className="intervention-meta small muted"><Space wrap>
      {groups.find(group => group.id === item.group_id) && <Link to={`/groups/${item.group_id}`}>{groups.find(group => group.id === item.group_id)?.name}</Link>}
      {groups.find(group => group.id === item.group_id) && <Tag>{groups.find(group => group.id === item.group_id)?.phase_id === item.phase_id ? '当前阶段' : '此前阶段'}</Tag>}
      <Tag bordered={false}>{RULE_MODE_NAMES[item.mode] || item.mode}</Tag>
      <span>{item.target_user_id ? `面向 ${item.evidence.metrics?.students.find(student => student.user_id === item.target_user_id)?.name || '指定成员'}` : '面向全组'}</span>
      {item.published_at && <span>发布 {timeText(item.published_at)}</span>}
      {item.status === 'published' && !item.effect && <span>{groups.find(group => group.id === item.group_id)?.state === 'completed' ? '讨论已结束，复查停止' : <>复查等待 <Countdown deadline={item.review_at} /></>}</span>}
    </Space></div>
    {item.effect && <Alert className="intervention-review" type="info" message={item.effect.result === 'persists' ? '复查窗口仍观察到异常' : item.effect.result === 'phase-changed' ? '讨论已进入下一阶段' : item.effect.result === 'insufficient-data' ? '发布后的观察数据不足或尚未完成分析，暂无法判断变化' : '复查窗口未再观察到该异常'} description={`${item.effect.observed_messages == null ? '' : `发布后已分析 ${item.effect.observed_messages} 条，至少需要 ${item.effect.required_messages ?? '暂无数据'} 条。`}观察记录不能据此判断因果效果。`} />}
    <Collapse ghost size="small" items={[{ key: 'evidence', label: '查看触发依据与版本', children: <><p>{item.evidence.reason}</p>{item.evidence.agent_rationale && <p>生成依据：{item.evidence.agent_rationale}</p>}<p className="muted">{item.evidence.message_ids?.length || 0} 条原始消息 · {item.skill_slug} v{item.skill_version} · 课题配置 v{item.config_version} · {item.model}</p>{item.evidence.message_ids?.map(id => <Tag key={id}>{id.slice(0, 8)}</Tag>)}</> }]} />
    {['pending', 'notify', 'generating'].includes(item.status) && <div className="intervention-actions"><Space><Button size="small" loading={busy === item.id} onClick={() => void act(item, 'dismiss')}>忽略</Button>{item.status === 'pending' && <Button size="small" type="primary" loading={busy === item.id} onClick={() => void act(item, 'approve')}>确认并发布到小组</Button>}</Space></div>}
  </Card>)}</div> : <EmptyState title="暂无智能提示" description="启用课题规则后，符合持续观察条件的提示会出现在这里。也可以手动请求阶段总结。" />;
}

export function GroupPage() {
  const outcomeFormId = useId();
  const { groupId } = useParams();
  const { user } = useAuth();
  const teacher = user?.role === 'teacher';
  const resource = useResource<GroupDetail>(`/groups/${groupId}`);
  const group = resource.data;
  const connected = useTopicLive(group?.topic_id, resource.refresh);
  const { message, modal } = App.useApp();
  const [busy, setBusy] = useState<string>();
  const [text, setText] = useState('');
  const [reply, setReply] = useState<ChatMessage>();
  const sender = useRef<ComponentRef<typeof Sender>>(null);
  const discussion = useDiscussionMessages(group);
  const messages = discussion.messages;
  const [sending, setSending] = useState(false);
  const sendLock = useRef(false);
  const [unread, setUnread] = useState(0);
  const [outcomeOpen, setOutcomeOpen] = useState(false);
  const [inspectingId, setInspectingId] = useState<string>();
  const [correcting, setCorrecting] = useState<MeaningUnit>();
  const bottom = useRef<HTMLDivElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const previousNewest = useRef<string | undefined>(undefined);
  const readingAnchor = useRef<{ height: number; top: number } | undefined>(undefined);
  const currentGroup = useRef(groupId);
  currentGroup.current = groupId;
  const currentReply = useRef(reply);
  currentReply.current = reply;
  const pendingSend = useRef<{ content: string; reply_to: string | null; client_id: string } | undefined>(undefined);
  useEffect(() => { setText(''); setReply(undefined); setUnread(0); setSending(false); setInspectingId(undefined); sendLock.current = false; pendingSend.current = undefined; previousNewest.current = undefined; readingAnchor.current = undefined; follow.current = true; }, [groupId]);
  useLayoutEffect(() => {
    const element = scroll.current;
    if (!element || !messages.length) return;
    const newest = messages[messages.length - 1].id;
    if (readingAnchor.current) {
      const anchor = readingAnchor.current;
      element.scrollTop = anchor.top + element.scrollHeight - anchor.height;
      readingAnchor.current = undefined;
    } else if (follow.current) {
      element.scrollTop = element.scrollHeight;
      setUnread(0);
    } else if (previousNewest.current && previousNewest.current !== newest) {
      const previous = messages.findIndex(item => item.id === previousNewest.current);
      if (previous >= 0) setUnread(count => count + messages.length - previous - 1);
    }
    previousNewest.current = newest;
  }, [messages[0]?.id, messages.at(-1)?.id, messages.length]);
  const action = async (name: string) => {
    setBusy(name);
    try { await send(`/groups/${groupId}/control`, { action: name, expected_version: group?.version }); await resource.refresh(); }
    catch (error) { void message.error(errorMessage(error)); } finally { setBusy(undefined); }
  };
  const submit = async (value: string) => {
    if (!value.trim() || sendLock.current) return;
    if (value.trim().length > 4000) { void message.warning('消息最多 4000 字'); return; }
    sendLock.current = true;
    setSending(true);
    const body = pendingSend.current?.content === value.trim() && pendingSend.current.reply_to === (reply?.id || null)
      ? pendingSend.current : { content: value.trim(), reply_to: reply?.id || null, client_id: newClientId() };
    pendingSend.current = body;
    try {
      await send(`/groups/${groupId}/messages`, body);
      if (currentGroup.current !== groupId) return;
      setText(current => current.trim() === body.content ? '' : current);
      if ((currentReply.current?.id || null) === body.reply_to) setReply(undefined);
      pendingSend.current = undefined; follow.current = true; setUnread(0);
      if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
      await resource.refresh();
    } catch (error) { if (currentGroup.current === groupId) void message.error(errorMessage(error)); }
    finally { if (currentGroup.current === groupId) { sendLock.current = false; setSending(false); } }
  };
  const history = async () => {
    if (!messages.length || busy === 'history') return;
    setBusy('history');
    try {
      const result = await api<ChatMessage[]>(`/groups/${groupId}/messages?before_id=${encodeURIComponent(messages[0].id)}&limit=100`);
      if (currentGroup.current !== groupId) return;
      if (result.length && scroll.current) readingAnchor.current = { height: scroll.current.scrollHeight, top: scroll.current.scrollTop };
      discussion.appendHistory(result);
    } catch (error) { void message.error(errorMessage(error)); } finally { setBusy(undefined); }
  };
  const summarize = async () => { setBusy('summary'); try { await send(`/groups/${groupId}/summarize`); await resource.refresh(); void message.success('总结任务已提交，请在智能提示中确认'); } catch (error) { void message.error(errorMessage(error)); } finally { setBusy(undefined); } };
  if (!group) return <PageLoad error={resource.error} retry={resource.refresh} />;
  const metrics = group.metrics;
  const inspecting = metrics?.students.find(student => student.user_id === inspectingId);
  const canSend = teacher ? group.state !== 'completed' : group.state === 'active';
  return <><Link className="back-link" to={`/topics/${group.topic_id}`}><ArrowLeftOutlined /> {group.topic_title}</Link>
    <div className="page-heading group-page-heading"><div><span className="eyebrow">DISCUSSION / {group.name}</span><h1>{group.name}</h1><Space><StateTag state={group.state} /><LiveTag connected={connected} /><span className="muted">{group.member_count} 人 · {group.online_count} 人在线</span></Space></div>
      {teacher && <Space wrap>{group.state === 'waiting' && <Button type="primary" icon={<PlayCircleOutlined />} disabled={Boolean(group.start_blocked_reason)} loading={busy === 'start'} onClick={() => void action('start')}>开始讨论</Button>}
        {group.state === 'active' && <><Button icon={<PauseCircleOutlined />} loading={busy === 'pause'} onClick={() => void action('pause')}>暂停</Button><Button type="primary" icon={<ForwardOutlined />} loading={busy === 'advance'} onClick={() => modal.confirm({ title: group.phase_index === group.stages.length - 1 ? '完成这个小组的讨论？' : '进入下一讨论阶段？', content: '当前阶段的讨论与成果将保存，新阶段重新统计学习投入。', onOk: () => action('advance') })}>下一阶段</Button></>}
        {group.state === 'paused' && <Button type="primary" icon={<PlayCircleOutlined />} loading={busy === 'resume'} onClick={() => void action('resume')}>恢复讨论</Button>}
        {['active', 'paused'].includes(group.state) && <Button onClick={() => modal.confirm({ title: '结束小组讨论？', content: '讨论结束后不能继续发送消息，已有记录将保留。', onOk: () => action('complete') })}>结束</Button>}</Space>}
    </div><ErrorNotice error={resource.error || discussion.error} retry={resource.refresh} />
    {teacher && group.state === 'waiting' && group.start_blocked_reason && <Alert type="warning" showIcon message={group.start_blocked_reason} action={<Link to={`/topics/${group.topic_id}`}><Button size="small">返回课题整理分组</Button></Link>} className="form-alert" />}
    <div className="phase-banner"><StageTrack stages={group.stages} current={group.state === 'waiting' ? -1 : group.phase_index} completed={group.state === 'completed'} /><div><span className="muted small">{group.state === 'paused' ? '暂停剩余' : '阶段剩余'}</span><Countdown deadline={group.deadline} remaining={group.remaining_seconds} /></div></div>
    {teacher && <AssistantPanel group={group} />}
    <div className={`discussion-layout ${teacher ? 'teacher-discussion' : ''}`}><section className="chat-panel">
      <div className="chat-header"><h2><CommentOutlined /> 小组讨论</h2><Space><Button size="small" icon={<FileTextOutlined />} disabled={group.state !== 'active'} onClick={() => setOutcomeOpen(true)}>提交成果</Button>{teacher && <Button size="small" icon={<RobotOutlined />} loading={busy === 'summary'} disabled={group.state !== 'active'} onClick={() => void summarize()}>生成总结</Button>}</Space></div>
      <div className="chat-scroll" ref={scroll} onScroll={() => { const element = scroll.current; if (element) { follow.current = element.scrollHeight - element.scrollTop - element.clientHeight < 90; if (follow.current) setUnread(0); } }}>
        {messages.length < group.message_count && <div className="history-button"><Button type="link" loading={busy === 'history'} onClick={() => void history()}>加载更早消息</Button></div>}
        {messages.length ? messages.map(item => { const referenced = messages.find(m => m.id === item.reply_to); return <div className={`chat-message ${item.kind === 'ai' ? 'ai-message' : ''}`} key={item.id}>
          <Bubble placement={item.author_id === user?.id ? 'end' : 'start'} avatar={<Avatar style={{ background: item.kind === 'ai' ? '#e2eddf' : item.kind === 'teacher' ? '#dce8ff' : '#e9edf3', color: '#314760' }} icon={item.kind === 'ai' ? <RobotOutlined /> : undefined}>{item.kind !== 'ai' ? item.author_name.slice(-2) : null}</Avatar>}
            header={<span className="bubble-name">{item.author_name}{item.kind === 'teacher' && <Tag bordered={false} color="blue">老师</Tag>}<small>{timeText(item.created_at)}</small>{item.phase_id !== group.phase_id && <small>此前阶段</small>}</span>}
            content={<div>{item.reply_to && <div className="reply-quote">{referenced ? `回复 ${referenced.author_name}：${referenced.content.slice(0, 80)}` : '回复较早消息，加载历史后可查看原文'}</div>}<div className="preserve-text">{item.content}</div></div>}
            footer={<Space size={6}>{canSend && <Button type="text" size="small" onClick={() => { setReply(item); sender.current?.focus({ cursor: 'end' }); }}>回复</Button>}{teacher && item.kind === 'student' && <span className="analysis-label">{{ pending: '分析中', unconfigured: '待配置模型', failed: '分析失败', complete: '已分析' }[item.analysis_status] || item.analysis_status}</span>}</Space>} />
          {teacher && Boolean(item.units?.length) && <Collapse ghost size="small" className="message-coding" items={[{ key: 'coding', label: `编码依据 · ${item.units?.length} 个意义单元`, children: item.units?.map(unit => <UnitEvidence key={unit.id} unit={unit} onCorrect={() => setCorrecting(unit)} />) }]} />}
        </div>; }) : <EmptyState title="把第一个想法带进讨论" description={group.state === 'waiting' ? '老师开始讨论后，你就可以分享观点。' : '从你的观察、问题或经验开始。'} />}
        <div ref={bottom} />
      </div>{unread > 0 && <div className="new-message-bar"><Button type="link" onClick={() => { follow.current = true; setUnread(0); if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight; }}>查看新消息（{unread}）</Button></div>}{discussion.recovering && <div className="recovery-note" role="status">正在补齐断线期间的消息…</div>}
      <div className="chat-composer">{reply && <div className="reply-preview"><span>回复 {reply.author_name}：{reply.content.slice(0, 65)}</span><Button size="small" type="text" aria-label="取消回复" icon={<CloseOutlined />} onClick={() => setReply(undefined)} /></div>}
        <Sender ref={sender} value={text} onChange={setText} onSubmit={value => void submit(value)} loading={sending} disabled={!canSend} actions={(_, { components }) => <components.SendButton loading={sending} disabled={sending || !canSend || !text.trim()} aria-label="发送消息" />} placeholder={canSend ? '分享观点，或回应一个问题…' : group.state === 'paused' ? '讨论已暂停，等待老师恢复' : group.state === 'completed' ? '讨论已结束' : '等待老师开始讨论'} submitType="enter" />
        <div className="composer-note">Enter 发送 · Shift + Enter 换行<span className={text.length > 4000 ? 'text-limit' : ''}>{text.length}/4000</span></div>
      </div>
    </section><aside className="discussion-aside"><Card size="small" title="本组成员"><div className="member-list">{group.members.map(member => <div key={member.id}><Avatar size="small">{member.name.slice(-2)}</Avatar><span>{member.name}</span><i className={member.online ? 'online-dot' : 'offline-dot'} /></div>)}</div></Card>
      <Card size="small" title="讨论任务"><p className="preserve-text">{group.instructions}</p>{group.direction && <><strong>本组方向</strong><p>{group.direction}</p></>}{group.references && <Collapse ghost size="small" items={[{ key: 'reference', label: '查看参考资料', children: <p className="preserve-text">{group.references}</p> }]} />}</Card>
      <Card size="small" title="阶段成果">{group.outcomes.length ? group.outcomes.slice(0, 5).map(item => <div className="outcome-item" key={item.id}>
        <Tag>{item.phase_id === group.phase_id ? '当前阶段' : '此前阶段'}</Tag><span className="muted small">{timeText(item.created_at)}</span><p className="preserve-text">{item.content}</p>
      </div>) : <p className="muted">{group.state === 'completed' ? '本阶段未提交成果。' : group.state === 'paused' ? '恢复讨论后可提交阶段成果。' : group.state === 'waiting' ? '老师开始讨论后可提交阶段成果。' : '还未提交成果。归纳共识后，点击“提交成果”。'}</p>}</Card>
    </aside></div>
    {teacher && metrics && <div className="observatory"><SectionTitle title="学习投入观察" subtitle={`观察窗口 ${timeText(metrics.window_start)}–${timeText(metrics.window_end)} · 最近分析 ${timeText(metrics.last_analyzed_at)} · 编码覆盖 ${metrics.coverage == null ? '暂无数据' : `${Math.round(metrics.coverage * 100)}%`}`} />
      {metrics.pending_messages > 0 && <Alert type="info" showIcon className="form-alert" message={`${metrics.pending_messages} 条消息待分析。以下指标仅反映已有编码，尚不能代表完整讨论。`} />}
      {metrics.failed_messages > 0 && <Alert type="warning" showIcon className="form-alert" message={`${metrics.failed_messages} 条消息分析失败`} action={<Button size="small" onClick={async () => { try { const result = await send<{ retried: number }>(`/groups/${groupId}/retry-analysis`); void message.success(`已重新排队 ${result.retried} 个任务`); await resource.refresh(); } catch (error) { void message.error(errorMessage(error)); } }}>重试分析</Button>} />}
      <div className="summary-strip"><Metric label="有效参与 NA" value={`${metrics.NA}/${metrics.member_count}`} /><Metric label="有效消息 NS" value={metrics.NS} note="每条原始消息最多计一次" /><Metric label="最大间隔 Max_TS" value={durationText(metrics.Max_TS)} /><Metric label="阶段成果 TC" value={metrics.TC ? '已提交' : '未提交'} /></div>
      <Tabs items={[{ key: 'students', label: '学生情况', children: <Card><Table<StudentMetrics> rowKey="user_id" pagination={false} dataSource={metrics.students} scroll={{ x: 650 }} columns={[
        { title: '学生', dataIndex: 'name' }, { title: '在线', render: (_, row) => <Tag bordered={false} color={group.members.find(member => member.id === row.user_id)?.online ? 'success' : 'default'}>{group.members.find(member => member.id === row.user_id)?.online ? '在线' : '离线'}</Tag> }, { title: '有效发言', dataIndex: 'NS' }, { title: '当前沉默', render: (_, row) => durationText(row.silence_seconds) }, { title: '历史最大间隔', render: (_, row) => durationText(row.Max_TS) },
        { title: '最近活动', render: (_, row) => timeText(row.last_activity) }, { title: '查看依据', render: (_, row) => <Button type="link" onClick={() => setInspectingId(row.user_id)}>消息与编码</Button> },
      ]} /></Card> },
      { key: 'charts', label: '认知与互动', children: <MetricsCharts metrics={metrics} /> },
      { key: 'interventions', label: `智能提示${group.assistant?.pending_approval ? ` (${group.assistant.pending_approval})` : ''}`, children: <InterventionList items={group.interventions || []} refresh={resource.refresh} groups={[group]} /> },
      { key: 'jobs', label: '分析任务', children: <AnalysisTasks group={group} /> },
      ]} />
    </div>}
    <StableModal title="提交阶段成果" open={outcomeOpen} width={640} onCancel={() => setOutcomeOpen(false)} footer={<Space><Button onClick={() => setOutcomeOpen(false)}>取消</Button><Button type="primary" htmlType="submit" form={outcomeFormId} loading={busy === 'outcome'}>保存阶段成果</Button></Space>}><p className="muted">{group.stages[group.phase_index]?.name} · 记录共同结论、分歧或接下来要验证的问题。</p><Form id={outcomeFormId} scrollToFirstError={{ block: 'center' }} onFinish={async (values: { content: string }) => { setBusy('outcome'); try { await send(`/groups/${groupId}/outcomes`, values); setOutcomeOpen(false); await resource.refresh(); void message.success('成果已保存'); } catch (error) { void message.error(errorMessage(error)); } finally { setBusy(undefined); } }}><Form.Item name="content" rules={[{ required: true }, { min: 5, max: 10000 }]}><Input.TextArea rows={10} placeholder="我们的共同结论是…" aria-label="阶段成果" /></Form.Item></Form></StableModal>
    <Drawer title={`${inspecting?.name || ''} · 消息与编码依据`} open={Boolean(inspecting)} onClose={() => setInspectingId(undefined)} width={540}>
      <Alert type="info" showIcon message="情感编码只描述消息中外显表达，不代表对学生心理状态的诊断。" className="form-alert" />
      {inspecting && <Space wrap>{Object.entries(inspecting.emotion).map(([code, count]) => <Tag key={code}>{code} {EMOTION_NAMES[code]} {count}</Tag>)}</Space>}
      <p className="muted small">显示当前已加载的讨论记录；可在讨论区加载更早消息，查看其余依据。</p>
      {messages.filter(item => item.author_id === inspecting?.user_id).map(item => <Card size="small" key={item.id} className="evidence-message"><Tag>{item.phase_id === group.phase_id ? '当前阶段' : '此前阶段'}</Tag><span className="muted">{timeText(item.created_at)}</span><p className="preserve-text">{item.content}</p>{item.units?.map(unit => <UnitEvidence key={unit.id} unit={unit} onCorrect={() => setCorrecting(unit)} />)}</Card>)}
    </Drawer>
    <CorrectionModal unit={correcting} onClose={() => setCorrecting(undefined)} onSaved={async updated => { discussion.appendHistory(messages.filter(item => item.id === updated.message_id).map(item => ({ ...item, units: item.units?.map(unit => unit.id === updated.id ? updated : unit) }))); setCorrecting(undefined); await resource.refresh(); void message.success('编码修正已保存'); }} />
  </>;
}

function UnitEvidence({ unit, onCorrect }: { unit: MeaningUnit; onCorrect: () => void }) {
  return <div className="unit-evidence"><blockquote>{unit.quote}</blockquote><Space wrap size={3}><Tag color="blue">{unit.cognitive} {COGNITIVE_NAMES[Number(unit.cognitive.slice(1))]}</Tag><Tag>{unit.emotion} {EMOTION_NAMES[unit.emotion]}</Tag>{unit.metacognitive.map(code => <Tag key={code}>{code}</Tag>)}{unit.social.map(code => <Tag key={code}>{code}</Tag>)}{unit.corrected && <Tag color="gold">老师已修正</Tag>}</Space>
    <p>{unit.reason}</p><div className="unit-footer"><span>{Math.round(unit.confidence * 100)}% 置信度 · {unit.skill_slug} v{unit.skill_version} · {unit.model}</span><Button type="link" size="small" onClick={onCorrect}>修正</Button></div></div>;
}
function CorrectionModal({ unit, onClose, onSaved }: { unit?: MeaningUnit; onClose: () => void; onSaved: (updated: MeaningUnit) => Promise<void> }) {
  const formId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  return <StableModal title="修正意义单元编码" open={Boolean(unit)} width={640} onCancel={onClose} afterClose={() => setError(undefined)} footer={<Space><Button onClick={onClose}>取消</Button><Button htmlType="submit" form={formId} type="primary" loading={busy}>保存修正</Button></Space>}><blockquote className="preserve-text">{unit?.quote}</blockquote><p className="muted">保留原文跨度和版本，修正内容会写入课堂记录。</p>{error && <Alert type="error" message={error} className="form-alert" />}
    <Form id={formId} layout="vertical" scrollToFirstError={{ block: 'center' }} initialValues={unit} onFinish={async values => { setBusy(true); setError(undefined); try { const updated = await send<MeaningUnit>(`/units/${unit?.id}`, { ...unit, ...values }, 'PUT'); await onSaved(updated); } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); } }}>
      <div className="form-grid"><Form.Item name="cognitive" label="认知编码"><Select options={COGNITIVE_NAMES.map((label, index) => ({ label: `C${index} ${label}`, value: `C${index}` }))} /></Form.Item><Form.Item name="emotion" label="情感编码"><Select options={Object.entries(EMOTION_NAMES).map(([value, label]) => ({ label: `${value} ${label}`, value }))} /></Form.Item></div>
      <Form.Item name="task_relevant" label="属于有效任务话语" valuePropName="checked"><Switch /></Form.Item><Form.Item name="metacognitive" label="元认知"><Select mode="multiple" options={[{ label: 'M1 计划', value: 'M1' }, { label: 'M2 监控', value: 'M2' }, { label: 'M3 调整', value: 'M3' }]} /></Form.Item><Form.Item name="social" label="社会互动"><Select mode="multiple" options={['SS1', 'SS2', 'SS3', 'SS4', 'SS5'].map(value => ({ value, label: value }))} /></Form.Item>
      <Form.Item name="reason" label="修正依据" rules={[{ required: true }, { max: 1000 }]}><Input.TextArea rows={3} /></Form.Item>
    </Form></StableModal>;
}
export function MetricsCharts({ metrics }: { metrics: Metrics }) {
  const hasCoding = Object.values(metrics.cognitive).some(count => count > 0);
  const cognitive: EChartsOption = { tooltip: { trigger: 'axis' }, grid: { left: 24, right: 24, top: 24, bottom: 50, containLabel: true }, xAxis: { type: 'category', data: COGNITIVE_NAMES.map((name, i) => `C${i}\n${name}`), axisLabel: { fontSize: 11 }, axisTick: { show: false } }, yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#edf0f4' } } }, series: [{ type: 'bar', data: Object.values(metrics.cognitive), barWidth: 30, itemStyle: { color: '#376ab7', borderRadius: [4, 4, 0, 0] } }] };
  const graph: EChartsOption = { tooltip: {}, series: [{ type: 'graph', layout: 'circular', symbolSize: 44, roam: false, label: { show: true, color: '#253951', fontSize: 11 }, data: metrics.students.map(s => ({ id: s.user_id, name: s.name, value: s.NS, itemStyle: { color: s.NS ? '#dae6f8' : '#ebedf0' } })), links: metrics.edges, edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 8, lineStyle: { color: '#7c96b9', width: 1.5, curveness: 0.15 } }] };
  return <div className="chart-grid"><Card title="认知投入分布">{hasCoding ? <Chart option={cognitive} /> : <EmptyState title="暂无认知编码" description="消息完成分析后展示当前窗口的分布。" />}<p className="muted small">按意义单元统计。认知编码用于观察讨论内容，非必须依次通过的阶段。</p></Card><Card title="回复互动关系"><Chart option={graph} /><p className="muted small">仅使用明确回复关系构建有向边。</p><div className="mini-metrics"><Tooltip title="实际有向关系 / 所有可能有向关系"><span>SD <strong>{metrics.SD ?? '暂无'}</strong></span></Tooltip><Tooltip title="双向互动对 / 已互动关系对"><span>SR <strong>{metrics.SR ?? '暂无'}</strong></span></Tooltip><Tooltip title="有效消息数的原始方差"><span>SE <strong>{metrics.SE ?? '暂无'}</strong></span></Tooltip><Tooltip title="凝聚度计算需经预实验确认，当前暂不计算，也不参与实时干预。"><span>SC <strong>暂无数据</strong></span></Tooltip></div></Card><Card title="元认知调节"><Space wrap>{Object.entries(METACOGNITIVE_NAMES).map(([code, name]) => <Tag key={code}>{code} {name} {hasCoding ? metrics.metacognitive?.[code] ?? 0 : '暂无数据'}</Tag>)}</Space><p className="muted small">仅统计当前窗口中明确出现的任务调节话语。</p></Card><Card title="社会支持"><Space wrap>{Object.entries(SOCIAL_NAMES).map(([code, name]) => <Tag key={code}>{code} {name} {hasCoding ? metrics.social[code] : '暂无数据'}</Tag>)}</Space><p className="muted small">按意义单元统计明确的邀请、帮助、协调与鼓励。</p></Card></div>;
}
