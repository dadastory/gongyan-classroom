import { createRoot } from 'react-dom/client';
import { lazy, Suspense } from 'react';
import { App as AntApp, Button, Dropdown, Avatar, Result } from 'antd';
import { XProvider } from '@ant-design/x';
import zhCN from 'antd/locale/zh_CN';
import { BookOutlined, SettingOutlined, LogoutOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { BrowserRouter, Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth';
import { send, errorMessage } from './api';
import { PageLoad } from './components';
import { ErrorBoundary } from './error-boundary';
import './styles.css';

const LoginPage = lazy(() => import('./pages/home').then(module => ({ default: module.LoginPage })));
const TopicsPage = lazy(() => import('./pages/home').then(module => ({ default: module.TopicsPage })));
const TopicPage = lazy(() => import('./pages/topic').then(module => ({ default: module.TopicPage })));
const GroupPage = lazy(() => import('./pages/group').then(module => ({ default: module.GroupPage })));
const SettingsPage = lazy(() => import('./pages/settings').then(module => ({ default: module.SettingsPage })));
const PresentationPage = lazy(() => import('./pages/presentation').then(module => ({ default: module.PresentationPage })));

function Shell() {
  const { user, loading, setUser, error, retry } = useAuth();
  const { message } = AntApp.useApp();
  const location = useLocation();
  const navigate = useNavigate();
  if (loading || error) return <PageLoad error={error} retry={retry} />;
  if (!user) return <Navigate to={`/login${location.search}`} replace state={{ from: location.pathname }} />;
  if (location.pathname.includes('/presentation')) return <Outlet />;
  const logout = async () => {
    try { await send('/auth/logout'); setUser(null); navigate('/login'); }
    catch (error) { void message.error(errorMessage(error)); }
  };
  return <div className="app-shell">
    <aside className="sidebar">
      <Link to="/" className="brand"><span className="brand-mark">共</span><span>共研<small>课堂协作学习</small></span></Link>
      <div className="workspace-label">{user.role === 'teacher' ? '教师工作空间' : '我的学习空间'}</div>
      <nav><Link to="/" className={!location.pathname.startsWith('/settings') ? 'selected' : ''}><BookOutlined />我的课题</Link>
        {user.role === 'teacher' && <Link to="/settings" className={location.pathname === '/settings' ? 'selected' : ''}><SettingOutlined />智能助教设置</Link>}</nav>
      <div className="sidebar-note"><span className="note-line" /><p>让每个声音<br />参与共同思考。</p><small>一起探索 · 一起建构</small></div>
      <Dropdown menu={{ items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: () => void logout() }] }} trigger={['click']}>
        <button className="user-menu" aria-label="打开账号菜单"><Avatar style={{ background: '#e6ecf5', color: '#223750' }}>{user.name.slice(-2)}</Avatar>
          <span>{user.name}<small>{user.role === 'teacher' ? '老师' : '学生'}</small></span><span>⌄</span></button>
      </Dropdown>
    </aside>
    <div className="workspace"><header className="topbar"><div className="mobile-brand"><Link to="/">共研</Link></div>
      <span className="breadcrumb">学习空间 <span>/</span> {location.pathname.startsWith('/settings') ? '智能助教' : location.pathname.startsWith('/groups') ? '小组讨论' : location.pathname.startsWith('/topics') ? '课题工作台' : '课题总览'}</span>
      <span className="topbar-right">{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })}<span className="role-pill">{user.role === 'teacher' ? '教师端' : '学生端'}</span><Dropdown trigger={['click']} menu={{ items: [
        ...(user.role === 'teacher' ? [{ key: 'settings', label: '智能助教设置', onClick: () => navigate('/settings') }] : []),
        { key: 'logout', label: '退出登录', onClick: () => void logout() },
      ] }}><Button className="mobile-user" type="text" size="small">{user.name} ⌄</Button></Dropdown></span>
    </header><main className="page-content"><Outlet /></main></div>
  </div>;
}
function TeacherOnly() { const { user } = useAuth(); return user?.role === 'teacher' ? <Outlet /> : <Result status="403" title="此页面仅对老师开放" extra={<Link to="/">返回我的课题</Link>} />; }
function Missing() { const navigate = useNavigate(); return <Result status="404" title="没有找到这个页面" extra={<Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>返回课题列表</Button>} />; }
createRoot(document.getElementById('root')!).render(
  <XProvider locale={zhCN} button={{ autoInsertSpace: false }} theme={{ token: { colorPrimary: '#245ab0', colorText: '#24344a', colorBgLayout: '#f5f6f8',
    colorBorder: '#dde3eb', borderRadius: 8, fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif', controlHeight: 36 },
    components: { Button: { primaryShadow: 'none' }, Card: { headerFontSize: 14, headerHeight: 46, bodyPadding: 18 },
      Form: { itemMarginBottom: 16 }, Tabs: { horizontalItemGutter: 24 } } }}>
    <AntApp><ErrorBoundary><BrowserRouter><AuthProvider><Suspense fallback={<PageLoad />}><Routes><Route path="/login" element={<LoginPage />} />
      <Route element={<Shell />}><Route index element={<TopicsPage />} /><Route path="/topics/:topicId" element={<TopicPage />} />
        <Route path="/groups/:groupId" element={<GroupPage />} /><Route element={<TeacherOnly />}>
          <Route path="/settings" element={<SettingsPage />} /><Route path="/topics/:topicId/presentation" element={<PresentationPage />} />
        </Route><Route path="*" element={<Missing />} /></Route>
    </Routes></Suspense></AuthProvider></BrowserRouter></ErrorBoundary></AntApp>
  </XProvider>,
);
