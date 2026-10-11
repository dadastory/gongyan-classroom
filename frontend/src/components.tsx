import { useEffect, useRef, useState } from 'react';
import { Alert, Avatar, Button, Empty, Skeleton, Space, Tag, Tooltip } from 'antd';
import { ReloadOutlined, TeamOutlined } from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { BarChart, GraphChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsOption } from 'echarts';
import { STATE_COLORS, STATE_NAMES } from './constants';
import type { Member } from './types';

echarts.use([BarChart, GraphChart, GridComponent, TooltipComponent, CanvasRenderer]);

export function PageLoad({ error, retry }: { error?: string; retry?: () => unknown }) {
  if (error) return <div className="load-state"><Alert type="error" showIcon message="暂时无法加载" description={error}
    action={<Space wrap>{retry && <Button onClick={() => retry()} icon={<ReloadOutlined />}>重试</Button>}<a href="/">返回课题列表</a></Space>} /></div>;
  return <div className="load-state"><Skeleton active paragraph={{ rows: 6 }} /></div>;
}
export function EmptyState({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return <div className="empty-state"><Empty image={<TeamOutlined style={{ fontSize: 48, color: '#a0adbc' }} />}
    description={<><h3>{title}</h3>{description && <p>{description}</p>}</>} />{action}</div>;
}
export function StateTag({ state }: { state: string }) { return <Tag bordered={false} color={STATE_COLORS[state]}>{STATE_NAMES[state] || state}</Tag>; }
export function LiveTag({ connected }: { connected: boolean }) { return <span className={`live-status ${connected ? '' : 'offline'}`}><i />{connected ? '实时连接' : '正在重连'}</span>; }
export function Members({ members, size = 'small' }: { members: Member[]; size?: 'small' | 'default' }) {
  return <Avatar.Group size={size} max={{ count: 6 }}>
    {members.map((member, index) => <Tooltip title={`${member.name}${member.online ? ' · 在线' : ''}`} key={member.id}>
      <Avatar style={{ background: ['#dde8fa', '#e4ebd7', '#f4e5d3', '#e7e0ef', '#dceee9', '#e5e9ed'][index % 6], color: '#33445b' }}>
        {member.name.slice(-2)}</Avatar></Tooltip>)}
  </Avatar.Group>;
}
export function Metric({ label, value, suffix, note }: { label: string; value: React.ReactNode; suffix?: string; note?: string }) {
  return <div className="metric"><span className="metric-label">{label}</span><div className="metric-number">{value}<small>{suffix}</small></div>{note && <span className="metric-note">{note}</span>}</div>;
}
export function SectionTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return <div className="section-title"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>;
}
export function Chart({ option, height = 240 }: { option: EChartsOption; height?: number }) {
  const element = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | undefined>(undefined);
  const latestOption = useRef(option);
  latestOption.current = option;
  const sync = useRef<(() => void) | undefined>(undefined);
  useEffect(() => {
    const container = element.current;
    if (!container) return;
    let applied: EChartsOption | undefined;
    const update = () => {
      const width = container.clientWidth;
      const measuredHeight = container.clientHeight;
      // 保留隐藏页签中的最新数据，恢复可见后再绘图；零宽度会使关系图的变换不可逆。
      if (width <= 0 || measuredHeight <= 0) return;
      const instance = chart.current ||= echarts.init(container, undefined, { width, height: measuredHeight });
      if (instance.getWidth() !== width || instance.getHeight() !== measuredHeight) instance.resize({ width, height: measuredHeight });
      if (applied !== latestOption.current) { instance.setOption(latestOption.current, true); applied = latestOption.current; }
    };
    sync.current = update;
    const observer = new ResizeObserver(update);
    observer.observe(container);
    update();
    return () => { observer.disconnect(); sync.current = undefined; chart.current?.dispose(); chart.current = undefined; };
  }, []);
  useEffect(() => { sync.current?.(); }, [option]);
  return <div ref={element} style={{ height }} role="img" aria-label="学习投入统计图表" />;
}
export function Countdown({ deadline, remaining }: { deadline: number | null; remaining?: number | null }) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now() / 1000), 1000); return () => clearInterval(timer); }, []);
  const seconds = deadline ? Math.max(0, deadline - now) : remaining;
  if (seconds == null) return <span className="countdown">—</span>;
  return <span className={`countdown ${seconds <= 60 ? 'urgent' : ''}`}>{String(Math.floor(seconds / 60)).padStart(2, '0')}:{String(Math.floor(seconds % 60)).padStart(2, '0')}</span>;
}
export function ErrorNotice({ error, retry }: { error?: string; retry: () => unknown }) {
  return error ? <Alert className="error-notice" type="warning" showIcon message="更新暂时失败，正在保留当前内容" description={error}
    action={<Button size="small" onClick={() => retry()}>重试</Button>} /> : null;
}
export function StageTrack({ stages, current, completed }: { stages: { name: string }[]; current: number; completed?: boolean }) {
  return <div className="stage-track">{stages.map((stage, index) => <div key={index} className={`stage ${index < current || completed ? 'done' : index === current ? 'current' : ''}`}>
    <span className="stage-dot">{index < current || completed ? '✓' : index + 1}</span><span>{stage.name}</span></div>)}</div>;
}
export function FormActions({ children }: { children: React.ReactNode }) { return <div className="form-actions"><Space>{children}</Space></div>; }
