import { useId, useRef, useState } from 'react';
import { App, Alert, Button, Card, Form, Input, InputNumber, Select, Space, Table, Tabs, Tag, Timeline, Popconfirm } from 'antd';
import { ProTable } from '@ant-design/pro-components';
import { ArrowLeftOutlined, ArrowRightOutlined, SettingOutlined, TeamOutlined, PlayCircleOutlined, PauseCircleOutlined, DesktopOutlined, CopyOutlined, PlusOutlined, ReloadOutlined, DownloadOutlined } from '@ant-design/icons';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { send, useResource, useTopicLive, errorMessage } from '../api';
import { useAuth } from '../auth';
import { PageLoad, StateTag, LiveTag, Metric, SectionTitle, Members, EmptyState, ErrorNotice, Countdown, StageTrack } from '../components';
import { EVENT_NAMES, timeText } from '../constants';
import { TopicEditor } from './topic-editor';
import { InterventionList } from './group';
import type { Group, GroupPlan, GroupPlanItem, Member, TopicDetail } from '../types';
import { StableModal } from '../stable-modal';
import { SupportTag } from '../observation';

export function TopicPage() {
  const { topicId } = useParams();
  const { user } = useAuth();
  const teacher = user?.role === 'teacher';
  const resource = useResource<TopicDetail>(`/topics/${topicId}`);
  const connected = useTopicLive(topicId, resource.refresh);
  const [editing, setEditing] = useState(false);
  const [grouping, setGrouping] = useState(false);
  const [busy, setBusy] = useState<string>();
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const act = async (action: string) => {
    setBusy(action);
    try { await send(`/topics/${topicId}/control`, { action }); await resource.refresh(); }
    catch (error) { void message.error(errorMessage(error)); } finally { setBusy(undefined); }
  };
  if (!resource.data) return <PageLoad error={resource.error} retry={resource.refresh} />;
  const topic = resource.data;
  const copy = async () => {
    try { await navigator.clipboard.writeText(`${location.origin}/?join=${topic.join_code}`); void message.success('加入链接已复制'); }
    catch { void message.info(`课题码：${topic.join_code}`); }
  };
  const joinGroup = async (group: Group) => {
    setBusy(group.id);
    try { await send(`/topics/${topicId}/groups/${group.id}/join`); await resource.refresh(); navigate(`/groups/${group.id}`); }
    catch (error) { void message.error(errorMessage(error)); } finally { setBusy(undefined); }
  };
  const cards = <div className="group-grid">{topic.groups.map((group, index) => <Card key={group.id} className="group-card">
    <div className="group-card-header"><span className="group-index">{String(index + 1).padStart(2, '0')}</span><StateTag state={group.state} /></div>
    <h3>{group.name}</h3><p className="muted group-direction">{group.direction || '共同探索课题，分享不同的视角。'}</p>
    <div className="group-stage"><span>{group.state !== 'waiting' ? topic.settings.stages[group.phase_index]?.name : '等待老师开始讨论'}</span>{group.state !== 'waiting' && <Countdown deadline={group.deadline} remaining={group.remaining_seconds} />}</div>
    {teacher && group.metrics && <div className="mini-metrics"><span>参与 <strong>{group.metrics.NA}/{group.member_count}</strong></span><span>有效发言 <strong>{group.metrics.NS}</strong></span><span>在线 <strong>{group.online_count}</strong></span></div>}
    {teacher && group.assistant && <div className="group-assistant-status"><SupportTag assistant={group.assistant} /><span className="muted small">待确认 {group.assistant.pending_approval} · 生成 {group.assistant.generating}{group.metrics?.pending_messages ? ` · 待分析 ${group.metrics.pending_messages}` : ''}</span></div>}
    {group.concerns?.length ? <Tag color="warning" bordered={false}>{group.concerns[0].reason}</Tag> : null}
    <div className="group-card-footer"><div>{group.members?.length ? <Members members={group.members} /> : <span className="muted"><TeamOutlined /> {group.member_count}/{group.capacity} 人</span>}</div>
      {teacher || topic.my_group_id === group.id ? <Link to={`/groups/${group.id}`}><Button type="text" icon={<ArrowRightOutlined />}>进入</Button></Link> : topic.settings.grouping_mode === 'self' && topic.status === 'preparing' ? <Button size="small" disabled={group.member_count >= group.capacity} loading={busy === group.id} onClick={() => void joinGroup(group)}>{group.member_count >= group.capacity ? '已满' : '加入小组'}</Button> : <Tag>{group.member_count} 人</Tag>}
    </div></Card>)}</div>;
  return <><Link className="back-link" to="/"><ArrowLeftOutlined /> 返回课题列表</Link>
    <div className="page-heading"><div><span className="eyebrow">TOPIC WORKSPACE</span><h1>{topic.title}</h1><Space><StateTag state={topic.status} /><LiveTag connected={connected} /><span className="muted">{topic.teacher_name} · {topic.student_count} 位学生</span></Space></div>
      {teacher && <Space wrap><Button icon={<SettingOutlined />} onClick={() => setEditing(true)}>课题设置</Button><Link to={`/topics/${topicId}/presentation`} target="_blank"><Button icon={<DesktopOutlined />}>课堂大屏</Button></Link></Space>}</div>
    <ErrorNotice error={resource.error} retry={resource.refresh} />
    {topic.is_demo && <Alert type="info" showIcon message="演示课堂：已有编码由演示样本提供，未经过真实模型分析。新消息会按你的模型配置处理。" className="form-alert" />}
    {teacher && topic.status === 'preparing' && <div className="invitation-banner"><div><span className="eyebrow">邀请学生加入</span><p>课题码 <strong className="join-code">{topic.join_code}</strong><Tag color={topic.join_open ? 'success' : 'default'}>{topic.join_open ? '加入入口开放中' : '加入入口已关闭'}</Tag></p></div><Button icon={<CopyOutlined />} onClick={() => void copy()}>复制加入链接</Button></div>}
    {!teacher && topic.my_group_id && <div className="invitation-banner"><div><h3>你已经加入讨论小组</h3><p className="muted">{topic.status === 'preparing' ? '进入小组，等待老师开始课堂。' : '查看讨论进展，继续和同伴交流。'}</p></div><Link to={`/groups/${topic.my_group_id}`}><Button type="primary" icon={<ArrowRightOutlined />}>进入我的小组</Button></Link></div>}
    <div className="summary-strip"><Metric label="参与学生" value={topic.student_count} suffix="人" /><Metric label="讨论小组" value={topic.group_count} suffix="组" /><Metric label="当前在线" value={topic.online_count} suffix="人" /><Metric label="讨论阶段" value={topic.settings.stages.length} suffix="个" /></div>
    <Tabs items={[
      { key: 'groups', label: '讨论工作台', children: <><SectionTitle title={teacher ? '小组进展' : '讨论小组'} subtitle={topic.status === 'preparing' ? topic.settings.grouping_mode === 'self' ? '选择感兴趣的讨论方向，加入一个小组。' : '学生加入后，由老师完成分组。' : '各小组独立推进，老师随时掌握进度。'} action={teacher && <Space wrap>
        {topic.status === 'preparing' ? <><Button onClick={() => setGrouping(true)} icon={<TeamOutlined />}>管理分组</Button><Button type="primary" icon={<PlayCircleOutlined />} disabled={Boolean(topic.start_blocked_reason)} loading={busy === 'start'} onClick={() => void act('start')}>开始课堂</Button></> : topic.status === 'active' ? <>
          {topic.groups.some(g => g.state === 'waiting') && <Button type="primary" loading={busy === 'start'} onClick={() => void act('start')}>开始其余小组</Button>}
          {topic.groups.some(g => g.state === 'active') && <Button icon={<PauseCircleOutlined />} loading={busy === 'pause'} onClick={() => void act('pause')}>暂停全部</Button>}
          {topic.groups.some(g => g.state === 'paused') && <Button loading={busy === 'resume'} onClick={() => void act('resume')}>恢复讨论</Button>}
          <Button type="primary" disabled={!topic.groups.some(g => g.state === 'active')} loading={busy === 'advance'} onClick={() => modal.confirm({ title: '推进正在讨论的小组？', content: '所有活跃小组进入下一阶段，最后阶段的小组将完成讨论。', onOk: () => act('advance') })}>下一阶段</Button></> : <Tag color="success">课堂已结束</Tag>}
      </Space>} />
        {teacher && topic.start_blocked_reason && <Alert type="warning" showIcon message={topic.start_blocked_reason} className="form-alert" />}
        {topic.groups.length ? cards : <EmptyState title="还没有讨论小组" description={teacher ? '等待学生加入后，创建或随机生成小组。' : '老师正在准备分组，请稍候。'} action={teacher && <Button onClick={() => setGrouping(true)}>管理分组</Button>} />}
      </> },
      { key: 'task', label: '课题任务', children: <Card><SectionTitle title="讨论内容" /><p className="preserve-text">{topic.description}</p>{topic.references && <><h3>参考资料</h3><p className="preserve-text">{topic.references}</p></>}<h3>讨论阶段</h3><StageTrack stages={topic.settings.stages} current={-1} /><p className="muted">{topic.settings.stages.map(s => `${s.name} ${s.minutes} 分钟`).join(' / ')}</p></Card> },
      ...(teacher ? [
        { key: 'students', label: `学生名单 (${topic.student_count})`, children: <ProTable<Member> rowKey="id" dataSource={topic.students || []} search={false} options={false} pagination={{ pageSize: 15 }} headerTitle="课堂成员" columns={[
          { title: '姓名', dataIndex: 'name' }, { title: '在线状态', dataIndex: 'online', render: (_, row) => <Tag color={row.online ? 'success' : 'default'}>{row.online ? '在线' : '离线'}</Tag> },
          { title: '讨论小组', render: (_, row) => topic.groups.find(g => g.id === row.group_id)?.name || <Tag color="warning">待分组</Tag> },
          ...(topic.status === 'preparing' ? [{ title: '操作', render: (_: unknown, row: Member) => <Popconfirm title="将这位学生移出课题？" description="只移出当前课题，账号和其他课题保留。" onConfirm={async () => { try { await send(`/topics/${topic.id}/students/${row.id}`, undefined, 'DELETE'); await resource.refresh(); void message.success('学生已移出当前课题'); } catch (error) { void message.error(errorMessage(error)); } }}><Button type="text" danger size="small">移出</Button></Popconfirm> }] : []),
        ]} /> },
        { key: 'interventions', label: `智能提示 ${topic.interventions?.filter(i => i.status === 'pending').length || ''}`, children: <InterventionList items={topic.interventions || []} refresh={resource.refresh} groups={topic.groups} /> },
        { key: 'records', label: '课堂记录', children: <Card><SectionTitle title="记录与数据" action={<Space><a href={`/api/topics/${topic.id}/export.csv`}><Button icon={<DownloadOutlined />}>消息 CSV</Button></a><a href={`/api/topics/${topic.id}/export.json`}><Button>完整研究数据</Button></a></Space>} /><Timeline items={(topic.events || []).map(event => ({ children: <><strong>{EVENT_NAMES[event.event] || event.event}</strong><span className="record-time">{timeText(event.created_at)}</span></> }))} /></Card> },
      ] : []),
    ]} />
    <TopicEditor open={editing} topic={topic} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); void resource.refresh(); void message.success('设置已保存'); }} />
    <GroupingModal open={grouping} topic={topic} onClose={() => setGrouping(false)} refresh={resource.refresh} />
  </>;
}

function GroupingModal({ open, topic, onClose, refresh }: { open: boolean; topic: TopicDetail; onClose: () => void; refresh: () => Promise<unknown> }) {
  const formId = useId();
  const bodyRef = useRef<HTMLDivElement>(null);
  const { message } = App.useApp();
  const [plan, setPlan] = useState<GroupPlan>();
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Group | 'new'>();
  const [error, setError] = useState<string>();
  const random = topic.settings.grouping_mode === 'random';
  const preview = async () => { setBusy(true); setError(undefined); try { setPlan(await send<GroupPlan>(`/topics/${topic.id}/random-preview`)); } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); } };
  const apply = async () => { setBusy(true); setError(undefined); try { await send(`/topics/${topic.id}/random-apply`, plan); await refresh(); onClose(); setPlan(undefined); void message.success('随机分组已应用'); } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); } };
  const switchEditor = (group?: Group | 'new') => {
    setEditing(group); setError(undefined);
    bodyRef.current?.closest('.ant-modal-body')?.scrollTo({ top: 0 });
  };
  const save = async (values: GroupPlanItem) => { setBusy(true); setError(undefined); try { await send(`/topics/${topic.id}/groups${editing !== 'new' && editing ? `/${editing.id}` : ''}`, { ...values, member_ids: values.member_ids || [] }, editing === 'new' ? 'POST' : 'PUT'); await refresh(); switchEditor(); void message.success('小组已保存'); } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); } };
  return <StableModal title={editing ? editing === 'new' ? '创建讨论小组' : '编辑讨论小组' : random ? '随机分组' : topic.settings.grouping_mode === 'self' ? '设置自主选择的小组' : '手动分组'} open={open} width={760} onCancel={onClose} afterClose={() => { setPlan(undefined); setEditing(undefined); setError(undefined); }}
    footer={editing ? <Space><Button icon={<ArrowLeftOutlined />} onClick={() => switchEditor()}>返回分组列表</Button><Button type="primary" htmlType="submit" form={formId} loading={busy}>保存小组</Button></Space> : random ? <Space><Button onClick={onClose}>取消</Button><Button icon={<ReloadOutlined />} loading={busy} onClick={() => void preview()}>生成预览</Button><Button type="primary" disabled={!plan} loading={busy} onClick={() => void apply()}>应用分组</Button></Space> : <Button onClick={onClose}>完成</Button>}>
    <div ref={bodyRef}>
    {editing ? <Form id={formId} key={editing === 'new' ? 'new' : editing.id} layout="vertical" scrollToFirstError={{ block: 'center' }} onFinish={save} initialValues={editing !== 'new' ? { ...editing, member_ids: editing.members?.map(m => m.id) || [] } : { capacity: topic.settings.group_size, member_ids: [] }}>
      {error && <Alert type="error" message={error} showIcon className="form-alert" />}<Form.Item name="name" label="小组名称" rules={[{ required: true }, { max: 80 }]}><Input /></Form.Item>
      <Form.Item name="direction" label="讨论方向"><Input.TextArea rows={3} maxLength={1000} /></Form.Item><Form.Item name="capacity" label="人数上限" rules={[{ required: true }]}><InputNumber min={2} max={15} /></Form.Item>
      <Form.Item name="member_ids" label="分配学生"><Select mode="multiple" optionFilterProp="label" options={topic.students?.map(s => ({ value: s.id, label: `${s.name}${s.group_id ? ` · ${topic.groups.find(g => g.id === s.group_id)?.name}` : ' · 未分组'}` }))} /></Form.Item>
    </Form> : <>
    <p className="muted">{random ? `按每组最多 ${topic.settings.group_size} 人均衡分组。预览不会修改现有分组，应用后替换准备阶段的小组。` : '设置讨论方向和容量，可以直接选取成员；已在其他组的成员会转移到当前组。'}</p>
    {error && <Alert type="error" message={error} showIcon className="form-alert" />}
    {random ? plan ? <Table<GroupPlanItem> pagination={false} rowKey="name" dataSource={plan.groups} columns={[{ title: '小组', dataIndex: 'name' }, { title: '人数', render: (_, row) => row.member_ids.length }, { title: '成员', render: (_, row) => row.member_ids.map(id => topic.students?.find(s => s.id === id)?.name).join('、') }]} /> : <EmptyState title="生成一份分组预览" description={`已加入 ${topic.student_count} 人。生成后检查名单，再应用分组。`} /> : <>
      <Button type="dashed" block icon={<PlusOutlined />} onClick={() => switchEditor('new')}>创建讨论小组</Button>
      <div className="group-management-list">{topic.groups.map(group => <div key={group.id}><span><strong>{group.name}</strong><small>{group.member_count}/{group.capacity} 人 · {group.direction || '未设置方向'}</small></span><Space><Button onClick={() => switchEditor(group)}>编辑与分配</Button><Popconfirm title="移除这个小组？" description="成员回到待分组；准备阶段消息会一并移除。" onConfirm={async () => { try { await send(`/topics/${topic.id}/groups/${group.id}`, undefined, 'DELETE'); await refresh(); } catch (error) { setError(errorMessage(error)); } }}><Button danger type="text">移除</Button></Popconfirm></Space></div>)}</div>
    </>}
    </>}
    </div>
  </StableModal>;
}
