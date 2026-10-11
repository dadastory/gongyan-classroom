import { Component } from 'react';
import type { ReactNode } from 'react';
import { Button, Result, Space } from 'antd';

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return <Result status="error" title="页面暂时遇到问题" subTitle="请重新加载页面；已保存的课堂记录仍会保留。"
      extra={<Space wrap><Button type="primary" onClick={() => window.location.reload()}>重新加载</Button><a href="/">返回课题列表</a></Space>} />;
  }
}
