import { useId, useState } from 'react';
import { App, Alert, Button, Card, Form, Input, Segmented, Tag } from 'antd';
import { ArrowRightOutlined, PlusOutlined, LoginOutlined, TeamOutlined, BookOutlined } from '@ant-design/icons';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { send, useResource, errorMessage } from '../api';
import { useAuth } from '../auth';
import { Metric, PageLoad, EmptyState, StateTag, ErrorNotice } from '../components';
import { TopicEditor } from './topic-editor';
import { StableModal } from '../stable-modal';
import type { User, Topic } from '../types';

export function LoginPage() {
  const { user, loading, setUser, error: authError, retry } = useAuth();
  const [register, setRegister] = useState(false);
  const [role, setRole] = useState<'student' | 'teacher'>('student');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [search] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const destination = search.get('join') ? `/?join=${encodeURIComponent(search.get('join')!)}` : (location.state as { from?: string } | null)?.from || '/';
  if (loading || authError) return <PageLoad error={authError} retry={retry} />;
  if (user) return <Navigate to={destination} replace />;
  const submit = async (values: Record<string, string>) => {
    setBusy(true); setError(undefined);
    try {
      const account = await send<User>(`/auth/${register ? 'register' : 'login'}`, { ...values, ...(register ? { role } : {}) });
      setUser(account); navigate(destination, { replace: true });
    } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); }
  };
  return <div className="login-layout"><section className="login-story">
    <div className="brand"><span className="brand-mark">共</span><span>共研<small>课堂协作学习</small></span></div>
    <div className="story-copy"><span className="eyebrow">A SPACE FOR SHARED THINKING</span><h1>好的讨论，<br />从听见彼此开始。</h1><p>把观点变成问题，把问题变成共同的理解。<br />在这里，每个人都是知识的参与者。</p></div>
    <div className="discussion-illustration" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><span className="thought t1">表达观点</span><span className="thought t2">提出问题</span><span className="thought t3">共同建构</span><div className="shared-center">一起<br /><strong>思考</strong></div><i className="dot d1" /><i className="dot d2" /><i className="dot d3" /></div>
    <footer>为协作学习而设计 <span>01 / EXPLORE TOGETHER</span></footer>
  </section><section className="login-panel"><div className="login-form"><span className="eyebrow">欢迎来到共研</span><h2>{register ? '创建你的学习账号' : '继续你的课堂讨论'}</h2><p className="muted">{register ? '选择身份，开启共同学习。' : '登录后进入课题，与同伴一起探索。'}</p>
    {register && <Segmented block className="role-select" value={role} onChange={value => setRole(value as typeof role)} options={[{ value: 'student', label: '我是学生' }, { value: 'teacher', label: '我是老师' }]} />}
    {error && <Alert type="error" showIcon message={error} className="form-alert" />}
    <Form layout="vertical" onFinish={submit} requiredMark={false} key={register ? 'register' : 'login'}>
      {register && <Form.Item name="name" label="姓名" rules={[{ required: true, whitespace: true, message: '请输入姓名' }, { max: 80 }]}><Input autoComplete="name" placeholder="你的姓名" /></Form.Item>}
      <Form.Item name="username" label="账号" rules={[{ required: true, message: '请输入账号' }, ...(register ? [{ pattern: /^[a-zA-Z0-9_.-]{3,80}$/, message: '使用 3–80 位字母、数字、点、下划线或短横线' }] : [])]}><Input autoComplete="username" placeholder="输入账号" /></Form.Item>
      <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, ...(register ? [{ min: 8, max: 128, message: '密码长度为 8–128 位' }] : [])]}><Input.Password autoComplete={register ? 'new-password' : 'current-password'} placeholder={register ? '至少 8 位' : '输入密码'} /></Form.Item>
      {register && role === 'teacher' && <Form.Item name="invite_code" label="老师邀请码" rules={[{ required: true, message: '请输入管理员提供的邀请码' }]}><Input placeholder="向平台管理员获取" /></Form.Item>}
      <Button block type="primary" size="large" htmlType="submit" loading={busy} icon={<ArrowRightOutlined />}>{register ? '创建账号' : '登录学习空间'}</Button>
    </Form><div className="login-switch">{register ? '已经有账号？' : '第一次来到这里？'}<Button type="link" onClick={() => { setRegister(!register); setError(undefined); }}>{register ? '去登录' : '创建账号'}</Button></div>
    <div className="login-tip"><BookOutlined /><span>老师创建课题，学生通过课题码加入。<br />讨论进度与小组成员实时同步。</span></div>
    <Link to="/examples" className="example-login-entry"><strong>先看看一堂课如何展开 →</strong><span>免登录浏览真实模型案例 · 讨论、教育支架与教师干预全过程</span></Link>
  </div></section></div>;
}

export function TopicsPage() {
  const joinFormId = useId();
  const { user } = useAuth();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const resource = useResource<Topic[]>('/topics');
  const [filter, setFilter] = useState('all');
  const [creating, setCreating] = useState(false);
  const [joining, setJoining] = useState(Boolean(search.get('join')));
  const [busy, setBusy] = useState(false);
  const [joinError, setJoinError] = useState<string>();
  const teacher = user?.role === 'teacher';
  const join = async (values: { code: string }) => {
    setBusy(true); setJoinError(undefined);
    try { const topic = await send<Topic>('/topics/join', values); setJoining(false); setSearch({}); navigate(`/topics/${topic.id}`); }
    catch (error) { setJoinError(errorMessage(error)); } finally { setBusy(false); }
  };
  if (!resource.data) return <PageLoad error={resource.error} retry={resource.refresh} />;
  const topics = resource.data.filter(topic => filter === 'all' || topic.status === filter);
  return <><div className="page-heading"><div><span className="eyebrow">CLASSROOM / {teacher ? 'TEACHER' : 'STUDENT'}</span><h1>{teacher ? '我的课题' : '一起探索新的问题'}</h1><p>{teacher ? '组织一场讨论，看见每个人的学习进展。' : `${user?.name}，欢迎回来。选择课题，继续共同学习。`}</p></div>
    <Button type="primary" icon={teacher ? <PlusOutlined /> : <LoginOutlined />} onClick={() => teacher ? setCreating(true) : setJoining(true)}>{teacher ? '创建课题' : '加入课题'}</Button></div>
    <ErrorNotice error={resource.error} retry={resource.refresh} />
    <div className="summary-strip"><Metric label="全部课题" value={resource.data.length} /><Metric label="正在进行" value={resource.data.filter(t => t.status === 'active').length} /><Metric label={teacher ? '课题参与人次' : '已完成课题'} value={teacher ? resource.data.reduce((sum, t) => sum + t.student_count, 0) : resource.data.filter(t => t.status === 'completed').length} /><div className="summary-note"><span>SHARED LEARNING</span><p>从独立观点，到共同理解。</p></div></div>
    <div className="list-toolbar"><h2>课题空间 <small>{topics.length}</small></h2><Segmented value={filter} onChange={setFilter} options={[{ label: '全部', value: 'all' }, { label: '准备中', value: 'preparing' }, { label: '进行中', value: 'active' }, { label: '已完成', value: 'completed' }]} /></div>
    {topics.length ? <div className="topic-grid">{topics.map((topic, index) => <Card key={topic.id} className="topic-card" hoverable>
      <div className="topic-card-top"><span className={`topic-icon tone-${index % 3}`}><BookOutlined /></span><StateTag state={topic.status} /></div>
      {topic.is_demo && <Tag bordered={false}>演示数据</Tag>}<Link to={`/topics/${topic.id}`} className="topic-title">{topic.title}</Link><p className="topic-description">{topic.description}</p>
      <div className="topic-facts"><span><TeamOutlined /> {topic.student_count} 位学生</span><span>{topic.group_count} 个小组</span></div>
      <div className="topic-card-bottom"><span>{new Date(topic.created_at * 1000).toLocaleDateString('zh-CN')}</span><Link to={`/topics/${topic.id}`}>进入课题 <ArrowRightOutlined /></Link></div>
    </Card>)}</div> : <EmptyState title={filter === 'all' ? '你的第一个课题，从这里开始' : '暂时没有这类课题'} description={teacher ? '设定一个值得讨论的问题，邀请学生加入。' : '向老师获取 6 位课题码，加入课堂。'} action={<Button onClick={() => teacher ? setCreating(true) : setJoining(true)}>{teacher ? '创建课题' : '加入课题'}</Button>} />}
    <TopicEditor open={creating} onClose={() => setCreating(false)} onSaved={topic => { setCreating(false); void message.success('课题已创建'); navigate(`/topics/${topic.id}`); }} />
    <StableModal title="加入课题" size="compact" open={joining && !teacher} footer={<Button type="primary" htmlType="submit" form={joinFormId} loading={busy}>加入课题</Button>} onCancel={() => { setJoining(false); setSearch({}); }} afterClose={() => setJoinError(undefined)}>
      <p className="muted">输入老师提供的 6 位课题码。</p>{joinError && <Alert type="error" message={joinError} showIcon className="form-alert" />}
      <Form id={joinFormId} layout="vertical" scrollToFirstError={{ block: 'center' }} onFinish={join} initialValues={{ code: search.get('join') || '' }}><Form.Item name="code" label="课题码" rules={[{ required: true }, { len: 6, message: '课题码应为 6 位' }]}><Input placeholder="例如 AB12CD" size="large" maxLength={6} style={{ textTransform: 'uppercase', letterSpacing: 5 }} /></Form.Item></Form>
    </StableModal>
  </>;
}
