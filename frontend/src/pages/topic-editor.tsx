import { useId, useState } from 'react';
import { Alert, Button, Collapse, Form, Input, InputNumber, Select, Space, Switch, Radio } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { send, useResource, errorMessage } from '../api';
import { DEFAULT_SETTINGS, RULE_NAMES } from '../constants';
import type { Skill, Topic, TopicDetail, TopicSettings } from '../types';
import { StableModal } from '../stable-modal';

interface Values { title: string; description: string; references: string; join_open: boolean; settings: TopicSettings }
export function TopicEditor({ open, topic, onClose, onSaved }: { open: boolean; topic?: TopicDetail; onClose: () => void; onSaved: (topic: Topic) => void }) {
  const formId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const { data: skills } = useResource<Skill[]>(open ? '/ai/skills' : null);
  const locked = topic && topic.status !== 'preparing';
  const save = async (values: Values) => {
    setBusy(true); setError(undefined);
    try { const result = await send<Topic>(topic ? `/topics/${topic.id}` : '/topics', values, topic ? 'PUT' : 'POST'); onSaved(result); }
    catch (error) { setError(errorMessage(error)); } finally { setBusy(false); }
  };
  return <StableModal title={topic ? '课题设置' : '创建课题'} open={open} width={780} onCancel={onClose} afterClose={() => setError(undefined)}
    footer={<Space><Button onClick={onClose}>取消</Button><Button type="primary" htmlType="submit" form={formId} loading={busy}>{topic ? '保存设置' : '创建课题'}</Button></Space>}>
    <Form id={formId} layout="vertical" requiredMark={false} scrollToFirstError={{ block: 'center' }} onFinish={save} initialValues={topic || { references: '', join_open: true, settings: structuredClone(DEFAULT_SETTINGS) }}>
      {error && <Alert type="error" showIcon message={error} className="form-alert" />}
      <Form.Item name="title" label="课题主题" rules={[{ required: true }, { min: 2, max: 120 }]}><Input placeholder="一个值得共同探索的问题" /></Form.Item>
      <Form.Item name="description" label="讨论内容与任务" rules={[{ required: true }, { min: 5, max: 20000 }]}><Input.TextArea rows={4} placeholder="背景、讨论问题、任务目标与成果要求" /></Form.Item>
      <Form.Item name="references" label="参考资料"><Input.TextArea rows={2} maxLength={20000} placeholder="阅读材料、链接或补充说明" /></Form.Item>
      <div className="form-grid"><Form.Item name="join_open" label="开放学生加入" valuePropName="checked"><Switch disabled={Boolean(locked)} /></Form.Item>
        <Form.Item name={['settings', 'group_size']} label="默认小组人数"><InputNumber min={2} max={15} disabled={Boolean(locked)} /></Form.Item></div>
      <Form.Item name={['settings', 'grouping_mode']} label="分组方式"><Radio.Group disabled={Boolean(locked)} options={[{ label: '老师手动分组', value: 'manual' }, { label: '随机均衡分组', value: 'random' }, { label: '学生自主选组', value: 'self' }]} /></Form.Item>
      <Form.List name={['settings', 'stages']} rules={[{ validator: async (_, stages) => { if (!stages?.length || stages.length > 8) throw new Error('请设置 1–8 个讨论阶段'); } }]}>
        {(fields, { add, remove }, { errors }) => <><label className="field-label">讨论阶段</label><p className="muted small">老师手动推进阶段；倒计时到期后保留当前讨论。</p>{fields.map(field => <div className="stage-form-row" key={field.key}><span>{field.name + 1}</span>
          <Form.Item name={[field.name, 'name']} rules={[{ required: true }, { max: 60 }]}><Input placeholder="阶段名称" disabled={Boolean(locked)} /></Form.Item>
          <Form.Item name={[field.name, 'minutes']} rules={[{ required: true }]}><InputNumber min={1} max={180} addonAfter="分钟" disabled={Boolean(locked)} /></Form.Item>
          {!locked && <Button type="text" aria-label="删除阶段" icon={<MinusCircleOutlined />} onClick={() => remove(field.name)} />}</div>)}<Form.ErrorList errors={errors} />
          {!locked && <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ name: '', minutes: 8 })} block>添加阶段</Button>}</>}
      </Form.List>
      <Collapse className="rules-collapse" items={[{ key: 'rules', forceRender: true, label: '智能助教：触发条件与 skills', children: <>
        <Form.Item name={['settings', 'rules', 'enabled']} label="启用智能提示" valuePropName="checked"><Switch /></Form.Item>
        <Form.Item name={['settings', 'rules', 'mode']} label="提示发布方式"><Select options={[{ label: '老师确认后发布', value: 'approval' }, { label: '自动发布', value: 'automatic' }, { label: '只提醒老师', value: 'notify' }]} /></Form.Item>
        <div className="form-grid">
          {[['window_seconds', '观察窗口（秒）', 30, 1800], ['cooldown_seconds', '提示冷却（秒）', 30, 1800], ['persistent_count', '持续异常消息数', 2, 10], ['silence_seconds', '参与提醒阈值（秒）', 30, 1800], ['min_messages', '最少观察消息数', 2, 30]].map(([key, label, min, max]) => <Form.Item key={key} name={['settings', 'rules', String(key)]} label={label}><InputNumber min={Number(min)} max={Number(max)} /></Form.Item>)}
        </div>
        {Object.entries(RULE_NAMES).filter(([key]) => key !== 'summary').map(([key, label]) => <Form.Item key={key} name={['settings', 'rules', 'bindings', key]} label={`${label} → skill`}><Select loading={!skills} options={skills?.map(skill => ({ label: `${skill.title} · v${skill.version}`, value: skill.slug }))} /></Form.Item>)}
        <Alert type="info" showIcon message="单次困惑或消极表达不会触发提示。系统结合持续证据、任务参与和讨论进展判断，老师可查看依据并修正编码。" />
      </> }]} />
    </Form>
  </StableModal>;
}
