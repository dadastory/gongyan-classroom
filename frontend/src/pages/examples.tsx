import { Alert, Button, Card, Collapse, Empty, Select, Space, Table, Tabs, Tag, Timeline } from 'antd';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useResource } from '../api';
import { Chart, Metric, PageLoad, StageTrack, StateTag } from '../components';
import { useAuth } from '../auth';
import { COGNITIVE_NAMES, durationText, EMOTION_NAMES, EVENT_NAMES, INTERVENTION_NAMES, METACOGNITIVE_NAMES, RULE_MODE_NAMES, RULE_NAMES, SOCIAL_NAMES, SUPPORT_NAMES } from '../constants';
import type { AnalysisTask, ClassroomExample, ExampleSummary, GroupDetail, MeaningUnit, StudentMetrics } from '../types';

const stamp = (time: number) => new Date(time * 1000).toLocaleString('zh-CN', { hour12: false });
const taskNames: Record<string, string> = { complete: '已完成', pending: '排队 / 重试', running: '运行中', blocked: '待配置', failed: '失败', stale: '已过期' };

function Coding({ unit }: { unit: MeaningUnit }) {
  return <div className="example-unit"><blockquote>{unit.quote}</blockquote><Space wrap size={[4, 4]}>
    <Tag color="blue">{unit.cognitive} · {COGNITIVE_NAMES[Number(unit.cognitive.slice(1))]}</Tag>
    <Tag>{unit.emotion} · {EMOTION_NAMES[unit.emotion]}</Tag><Tag>{unit.task_relevant ? '任务相关' : '非任务'}</Tag>
    {unit.metacognitive.map(code => <Tag key={code}>{code} · {METACOGNITIVE_NAMES[code]}</Tag>)}
    {unit.social.map(code => <Tag key={code}>{code} · {SOCIAL_NAMES[code]}</Tag>)}
    {unit.corrected && <Tag color="gold">老师已修正</Tag>}
  </Space><p className="small muted">{unit.reason}</p><small className="muted">{unit.skill_slug} v{unit.skill_version} · 课题 v{unit.config_version} · 置信度 {Math.round(unit.confidence * 100)}%</small></div>;
}

function Discussion({ group }: { group: GroupDetail }) {
  return <div className="example-discussion"><section aria-label="原始讨论记录">
    {group.messages.length ? group.messages.map(message => <article key={message.id} className={`example-message example-message-${message.kind}`}>
      <div className="example-message-head"><strong>{message.author_name}</strong><Tag bordered={false}>{message.kind === 'ai' ? '智能助教' : message.kind === 'teacher' ? '老师' : '学生'}</Tag><time>{stamp(message.created_at)}</time></div>
      <p className="preserve-text">{message.content}</p>
      {message.reply_to && <small className="muted">回复本组消息 {message.reply_to}</small>}
      {message.kind === 'student' && <Collapse ghost size="small" items={[{ key: message.id, label: message.analysis_status === 'complete' ? `查看 ${message.units?.length || 0} 个意义单元及编码依据` : `分析${taskNames[message.analysis_status] || message.analysis_status}`,
        children: message.units?.length ? message.units.map(unit => <Coding key={unit.id} unit={unit} />) : <p className="muted">该时刻尚无有效分析，不填充推测结果。</p> }]} />}
    </article>) : <Empty description="此快照暂无讨论消息" />}
  </section><aside><Card size="small" title="当前阶段认知编码分布"><Chart height={190} option={{ animation: false, grid: { left: 30, right: 12, top: 20, bottom: 30 }, tooltip: {},
      xAxis: { type: 'category', data: COGNITIVE_NAMES.map((_, i) => `C${i}`) }, yAxis: { type: 'value', minInterval: 1 },
      series: [{ type: 'bar', barMaxWidth: 25, data: COGNITIVE_NAMES.map((_, i) => group.metrics?.cognitive[`C${i}`] || 0), itemStyle: { color: '#3e638d', borderRadius: [3, 3, 0, 0] } }] }} />
    <p className="small muted">C0–C5 是编码类别，讨论无需逐级通过。</p></Card>
    <Card size="small" title="指标说明"><p className="small">NS 统计有效原始学生消息，意义单元拆分、老师与助教发言不增加 NS。</p><p className="small">Max_TS 是历史最长有效发言间隔，沉默为保存时刻的观察值。样本不足显示暂无数据。</p><p className="small muted">学生姓名与情感仅来自本次模拟课堂，不是真实学生研究数据。</p></Card></aside></div>;
}

function Supports({ group }: { group: GroupDetail }) {
  return group.interventions?.length ? <div className="example-supports">{group.interventions.map(item => <Card key={item.id} size="small">
    <div className="example-message-head"><strong>{RULE_NAMES[item.rule] || item.rule}</strong><Tag color={item.status === 'published' ? 'success' : item.status === 'pending' ? 'warning' : 'default'}>{INTERVENTION_NAMES[item.status] || item.status}</Tag><time>{stamp(item.created_at)}</time></div>
    <p className="preserve-text">{item.content || item.evidence.reason}</p>
    <div className="small muted">{RULE_MODE_NAMES[item.mode]} · {item.skill_slug} v{item.skill_version} · 课题 v{item.config_version} · {item.model}</div>
    <Collapse ghost size="small" items={[{ key: 'evidence', label: '触发依据与后续观察', children: <>
      <p>{item.evidence.reason}</p>{item.evidence.agent_rationale && <p>{item.evidence.agent_rationale}</p>}
      <p className="small">原始证据：{item.evidence.message_ids?.join('、') || '暂无'}</p>
      {item.effect ? <Alert type="info" showIcon message={item.effect.result === 'not-observed' ? '复查窗口未再观察到该关注点' : item.effect.result === 'persists' ? '复查仍有关注点' : item.effect.result === 'phase-changed' ? '讨论已进入下一阶段' : '发布后观察数据不足'} description={`已分析 ${item.effect.observed_messages ?? '暂无'} 条后续消息，至少需 ${item.effect.required_messages ?? '暂无'} 条。观察记录不能用于判断因果效果。`} /> : <p className="muted">该快照尚无后续复查记录。</p>}
    </> }]} />
  </Card>)}</div> : <Empty description="该时刻暂无智能提示" />;
}

function Record({ example, group, capturedAt }: { example: ClassroomExample; group: GroupDetail; capturedAt: number }) {
  const events = example.events.filter(e => (!e.group_id || e.group_id === group.id) && e.created_at <= capturedAt);
  return <Timeline className="example-timeline" items={events.map(event => ({ key: event.id, color: event.event === 'analysis.attempt_failed' ? 'orange' : '#56738f',
    children: <><strong>{EVENT_NAMES[event.event] || event.event}</strong><time className="muted small"> {stamp(event.created_at)}</time>
      {['unit.corrected', 'analysis.attempt_failed', 'group.pause', 'group.advance'].includes(event.event) && <Collapse ghost size="small" items={[{ key: event.id, label: '查看记录详情', children: <pre className="example-json">{JSON.stringify(event.data, null, 2)}</pre> }]} />}</> }))} />;
}

function ExampleContent({ example }: { example: ClassroomExample }) {
  const [search, setSearch] = useSearchParams();
  const chosen = example.groups.find(g => g.id === search.get('group')) || example.groups[0];
  const points = example.checkpoints.filter(point => point.group.id === chosen?.id);
  const point = points.find(p => p.id === search.get('step')) || points.at(-1);
  const group = point?.group || chosen;
  const capturedAt = point?.captured_at || example.recorded_at;
  const set = (values: Record<string, string>) => setSearch({ ...Object.fromEntries(search), ...values }, { replace: true });
  if (!group) return <Empty description="这个案例暂无小组记录" />;
  const m = group.metrics;
  const assistant = group.assistant;
  return <><div className="example-case-heading"><div><span className="eyebrow">课堂过程档案 / {new Date(example.recorded_at * 1000).toLocaleDateString('zh-CN')}</span><h1>{example.title}</h1><p>{example.description}</p></div>
    <Button href={`/api/examples/${example.id}/download`} download>下载脱敏案例</Button></div>
    <Alert type="info" showIcon message="模拟师生输入 · 真实模型调用 · 只读历史记录" description={example.source_note} />
    <ol className="example-flow" aria-label="教育智能体与协作平台集成机制">{[
      ['原始讨论', '消息、回复与阶段成果'], ['四维投入编码', '认知 · 行为 · 社会 · 情感'], ['持续状态判断', '证据窗口 · 规则 · 冷却'], ['教育支架', '自动发布 / 教师确认 / 仅提醒'], ['后续观察', '保留过程，不推断因果'],
    ].map(([title, note], i) => <li key={title}><span>{String(i + 1).padStart(2, '0')}</span><div><strong>{title}</strong><small>{note}</small></div></li>)}</ol>
    <div className="example-layout"><aside className="example-group-list"><h2>讨论小组 <small>{example.groups.length}</small></h2>
      {example.groups.map(g => <button type="button" aria-pressed={g.id === group.id} key={g.id} onClick={() => set({ group: g.id, step: '' })}><strong>{g.name}</strong><span>{g.member_count} 位成员 · {g.messages.filter(msg => msg.kind === 'student').length} 条学生消息</span></button>)}
      <div className="example-source small muted">模型：{example.model}<br />本案例 {example.student_count} 名模拟学生<br />历史记录不触发模型请求</div>
    </aside><section className="example-main"><div className="example-snapshot-toolbar"><div><h2>{group.name} <StateTag state={group.state} /></h2><span className="small muted">快照时间 {stamp(capturedAt)} · 历史在线 {group.online_count} 人</span></div>
      <Select aria-label="选择过程快照" value={point?.id} options={points.map(p => ({ value: p.id, label: `${new Date(p.captured_at * 1000).toLocaleTimeString('zh-CN', { hour12: false })} · ${p.label}` }))} onChange={value => set({ step: value })} /></div>
      <StageTrack stages={group.stages} current={group.phase_index} completed={group.state === 'completed'} />
      <div className="summary-strip example-metrics"><Metric label="有效发言 NS" value={m?.NS ?? '暂无'} /><Metric label="有效参与 NA" value={m?.NA ?? '暂无'} suffix={`/ ${group.member_count}`} /><Metric label="历史最长间隔 Max_TS" value={durationText(m?.Max_TS)} /><Metric label="阶段成果 TC" value={m?.TC ? '已提交' : '未提交'} /></div>
      {assistant && <Card size="small" className="example-assistant" title={<Space>该时刻助教状态<Tag>{SUPPORT_NAMES[assistant.status] || assistant.status}</Tag></Space>}>
        <div className="assistant-status-grid"><div><span>投入编码</span><strong>排队 {assistant.analysis_pending} · 运行 {assistant.analysis_running}</strong><small>失败 {assistant.analysis_failed} · 待配置 {assistant.analysis_blocked}</small></div><div><span>教育支架</span><strong>生成 {assistant.generating} · 待确认 {assistant.pending_approval}</strong><small>发布 {assistant.published} · 仅提醒 {assistant.notifications}</small></div><div><span>当前关注点</span><strong>{group.concerns?.map(c => RULE_NAMES[c.rule] || c.rule).join('、') || (m?.pending_messages ? '分析未完成' : '暂无持续关注点')}</strong><small>规则{assistant.rules_enabled ? '已启用' : '未启用'}</small></div><div><span>运行配置</span><strong>{RULE_MODE_NAMES[assistant.mode] || '手动总结'}</strong><small>窗口 {assistant.window_seconds} 秒 · 连接 v{assistant.connection_version ?? '暂无'}</small></div></div>
      </Card>}
      <Tabs className="example-tabs" activeKey={search.get('tab') || 'discussion'} onChange={value => set({ tab: value })} items={[
        { key: 'discussion', label: '讨论与编码', children: <Discussion group={group} /> },
        { key: 'students', label: '学生投入', children: <Table<StudentMetrics> size="small" rowKey="user_id" dataSource={m?.students} pagination={false} scroll={{ x: 620 }} columns={[
          { title: '模拟学生', dataIndex: 'name' }, { title: '有效发言 NS', dataIndex: 'NS' }, { title: '原始消息', dataIndex: 'total_messages' }, { title: '历史最长间隔', render: (_, s) => durationText(s.Max_TS) }, { title: '该时刻沉默', render: (_, s) => durationText(s.silence_seconds) },
        ]} /> },
        { key: 'supports', label: `教育支架 ${group.interventions?.length || 0}`, children: <Supports group={group} /> },
        { key: 'tasks', label: '分析任务', children: <Table<AnalysisTask> size="small" rowKey="id" dataSource={group.jobs} pagination={{ pageSize: 8 }} scroll={{ x: 680 }} columns={[
          { title: '任务', render: (_, t) => t.kind === 'analysis' ? '投入编码' : '支架生成' }, { title: '状态', render: (_, t) => <><Tag>{taskNames[t.status] || t.status}</Tag>{t.error && <p className="small">{t.error}</p>}</> }, { title: '尝试', dataIndex: 'attempts' },
          { title: '记录的运行版本', render: (_, t) => <div className="task-version">{t.skill_slug || '未开始'}{t.skill_version != null && ` v${t.skill_version}`}<small>{t.model || '尚未记录'} · 连接 v{t.connection_version ?? '暂无'} · 课题 v{t.config_version ?? '暂无'}</small></div> },
        ]} /> },
        { key: 'process', label: '过程记录', children: <Record example={example} group={group} capturedAt={capturedAt} /> },
        { key: 'integration', label: '智能体集成', children: <div className="example-integration"><Card size="small" title="持续状态与 Skill 绑定"><p className="small muted">持续规则根据有效消息、参与分布与观察窗口选择支架。单次 E2 / E3 不自动干预；情感支持还需满足发言减少、间隔增大及持续沉默等条件。</p><Table size="small" rowKey="rule" pagination={false} dataSource={Object.entries(example.settings.rules?.bindings || {}).map(([rule, slug]) => ({ rule, slug }))} columns={[
          { title: '持续状态', render: (_, row) => RULE_NAMES[row.rule] || row.rule }, { title: '加载的标准 Skill', dataIndex: 'slug' },
        ]} /></Card><Card size="small" title="执行与发布机制"><p>Python 后端通过 Agno SDK 加载标准 SKILL.md，调用教师配置的模型。</p><p className="small">编码结果先校验原文跨度与结构，再保存意义单元。状态判断使用持续规则，提示生成记录证据、skill、模型与课题版本。</p><p className="small">发布方式：{RULE_MODE_NAMES[example.settings.rules?.mode || 'approval']}；观察窗口 {example.settings.rules?.window_seconds} 秒；冷却 {example.settings.rules?.cooldown_seconds} 秒。</p><p className="small">暂停、换阶段或配置变化后，待发布提示失效。模型失败进入重试，原始消息保留。</p>
          <Collapse ghost size="small" items={example.skills.map(skill => ({ key: skill.id, label: `${skill.title} · ${skill.slug} v${skill.version}`, children: <pre className="example-json">{skill.markdown}</pre> }))} />
        </Card></div> },
        { key: 'outcomes', label: '阶段成果', children: group.outcomes.length ? group.outcomes.map(outcome => <Card key={outcome.id} size="small" title={stamp(outcome.created_at)}><p className="preserve-text">{outcome.content}</p><Tag>{outcome.phase_id === group.phase_id ? '当前阶段' : '此前阶段'}</Tag></Card>) : <Empty description="此快照暂无阶段成果" /> },
      ]} />
    </section></div>
    <Collapse className="example-verification" items={[{ key: 'checks', label: `查看实际验证结果与数据来源（${example.checks.length} 项）`, children: <><div className="example-checks">{example.checks.map(item => <div key={item.label}><Tag color="success">已验证</Tag><strong>{item.label}</strong><p className="muted small">{item.detail}</p></div>)}</div><p className="small muted">{example.provenance.method}</p><p className="small muted example-hash">原始研究导出 SHA-256：{example.provenance.source_sha256}</p></> }]} />
  </>;
}

export function ExamplesPage() {
  const { exampleId } = useParams();
  const { user } = useAuth();
  const list = useResource<ExampleSummary[]>('/examples');
  const selected = exampleId || list.data?.[0]?.id;
  const detail = useResource<ClassroomExample>(selected ? `/examples/${encodeURIComponent(selected)}` : null);
  return <div className="example-page"><header className="example-header"><Link to="/" className="brand"><span className="brand-mark">共</span><span>共研<small>课堂案例</small></span></Link><span className="muted small">教育智能体 × 在线协作学习</span><Link to={user ? '/' : '/login'}><Button>{user ? '返回学习空间' : '登录 / 创建课堂'}</Button></Link></header>
    <main className="example-container"><nav className="example-case-nav" aria-label="选择课堂案例">{list.data?.map(item => <Link key={item.id} className={item.id === selected ? 'selected' : ''} to={`/examples/${item.id}`}>{item.title}</Link>)}</nav>
      {list.error || detail.error ? <PageLoad error={list.error || detail.error} retry={() => { void list.refresh(); void detail.refresh(); }} /> : detail.data ? <ExampleContent key={detail.data.id} example={detail.data} /> : list.data?.length === 0 ? <Empty description="暂未安装课堂案例" /> : <PageLoad />}
    </main><footer className="example-footer">共研 · 课堂过程档案　/　模拟课堂输入与真实模型分析，供教学演示与功能了解</footer></div>;
}
