import { useId, useRef, useState } from 'react';
import { App, Alert, AutoComplete, Button, Card, Form, Input, Space, Tabs, Tag } from 'antd';
import { ProForm, ProFormText, ProFormDigit, ProFormSwitch, ProFormSelect } from '@ant-design/pro-components';
import { ApiOutlined, CheckCircleOutlined, EditOutlined, DownloadOutlined, PlusOutlined, HistoryOutlined } from '@ant-design/icons';
import { send, useResource, errorMessage } from '../api';
import { ErrorNotice, PageLoad, SectionTitle } from '../components';
import type { Connection, Skill } from '../types';
import { StableModal } from '../stable-modal';

export function SettingsPage() {
  const connection = useResource<Connection>('/ai/connection');
  const skills = useResource<Skill[]>('/ai/skills');
  const { message } = App.useApp();
  const [editing, setEditing] = useState<Skill | 'new'>();
  const [history, setHistory] = useState<Skill>();
  const versions = useResource<Skill[]>(history ? `/ai/skills/${history.slug}/versions` : null);
  if (!connection.data || !skills.data) return <PageLoad error={connection.error || skills.error} retry={() => { void connection.refresh(); void skills.refresh(); }} />;
  const config = connection.data;
  return <><div className="page-heading"><div><span className="eyebrow">INTELLIGENT TEACHING ASSISTANT</span><h1>智能助教设置</h1><p>连接模型，定义助教如何理解课堂、回应不同讨论情况。</p></div><Tag color={config.enabled && config.has_key ? 'success' : 'default'}>{config.enabled && config.has_key ? '模型连接已启用' : '等待配置模型'}</Tag></div>
    <ErrorNotice error={connection.error || skills.error} retry={() => { void connection.refresh(); void skills.refresh(); }} />
    <Tabs items={[{ key: 'connection', label: '模型连接', children: <div className="settings-grid"><Card title={<Space><ApiOutlined />模型 API</Space>}>
      <ModelConnectionForm key={config.version} config={config} onSaved={connection.refresh} />
    </Card><div><Card title="课堂中的助教"><p>助教首先把原始学生消息编码为意义单元，再结合参与、互动与持续表达判断是否需要支持。</p><p>进入课题设置，可以为不同情况选择 skill，决定自动发布、老师确认或只提醒老师。</p><Alert type="info" message="模型暂不可用时，学生仍可正常讨论。分析任务会保留，配置完成后可以继续处理。" showIcon /></Card><Card className="settings-note" title="统一的 skills"><p>使用标准 <code>SKILL.md</code>，每次编辑生成独立版本。课堂记录保存实际使用的 skill 和模型版本，便于复查。</p><p className="muted">运行引擎：Agno Python SDK。平台仅开放读取 skill 指令的能力。</p></Card></div></div> },
    { key: 'skills', label: `Skills (${skills.data.length})`, children: <><SectionTitle title="助教能力库" subtitle="统一维护分析、引导和总结指令，课题可以按讨论情况绑定不同能力。" action={<Button icon={<PlusOutlined />} type="primary" onClick={() => setEditing('new')}>新增 skill</Button>} />
      <div className="skill-grid">{skills.data.map(skill => <Card key={skill.slug}><div className="skill-title"><h3>{skill.title}</h3><Tag>v{skill.version}</Tag></div><code className="skill-slug">{skill.slug}</code><p>{skill.description}</p><Space wrap><Button size="small" icon={<EditOutlined />} onClick={() => setEditing(skill)}>编辑</Button><Button size="small" icon={<HistoryOutlined />} onClick={() => setHistory(skill)}>版本</Button><a href={`/api/ai/skills/${skill.slug}/download`}><Button size="small" icon={<DownloadOutlined />}>SKILL.md</Button></a></Space></Card>)}</div>
    </> }]} />
    <SkillEditor skill={editing} onClose={() => setEditing(undefined)} onSaved={async () => { setEditing(undefined); await skills.refresh(); void message.success('Skill 新版本已保存'); }} />
    <StableModal title={`${history?.title || ''} · 版本记录`} open={Boolean(history)} width={800} footer={<Button onClick={() => setHistory(undefined)}>关闭</Button>} onCancel={() => setHistory(undefined)}>
      {!versions.data ? <PageLoad error={versions.error} retry={versions.refresh} /> : <Tabs items={versions.data.map(version => ({ key: String(version.version), label: `v${version.version}`, children: <><p className="muted">{new Date(version.created_at * 1000).toLocaleString('zh-CN')} · SHA256 {version.digest.slice(0, 16)}</p><pre className="skill-preview">{version.markdown}</pre></> }))} />}
    </StableModal>
  </>;
}
type ConnectionDraft = Pick<Connection, 'base_url' | 'model' | 'output_mode' | 'timeout_seconds' | 'enabled'> & { api_key: string };
function ModelConnectionForm({ config, onSaved }: { config: Connection; onSaved: () => Promise<void> }) {
  const [form] = Form.useForm<ConnectionDraft>();
  const { message } = App.useApp();
  const [busy, setBusy] = useState<'models' | 'test'>();
  const [models, setModels] = useState<string[]>([]);
  const [catalogNote, setCatalogNote] = useState<string>();
  const [result, setResult] = useState<{ ok: boolean; text: string }>();
  const revision = useRef(0);
  const request = async (operation: 'models' | 'test') => {
    let values: ConnectionDraft;
    try { values = await form.validateFields(operation === 'models' ? ['base_url', 'api_key', 'timeout_seconds'] : undefined); } catch { return; }
    const current = revision.current;
    setBusy(operation); setResult(undefined);
    try {
      if (operation === 'models') {
        const response = await send<{ models: string[]; base_url: string; message: string; recommended_model?: string }>('/ai/models', values);
        if (revision.current !== current) return;
        form.setFieldsValue({ base_url: response.base_url, ...(!form.getFieldValue('model') && response.recommended_model ? { model: response.recommended_model } : {}) });
        setModels(response.models); setCatalogNote(response.message);
      } else {
        const response = await send<{ message: string; latency_ms: number; base_url: string }>('/ai/test-connection', values);
        if (revision.current !== current) return;
        form.setFieldsValue({ base_url: response.base_url });
        setResult({ ok: true, text: `${response.message} · ${(response.latency_ms / 1000).toFixed(1)} 秒` });
      }
    } catch (error) { if (revision.current === current) setResult({ ok: false, text: errorMessage(error) }); }
    finally { setBusy(undefined); }
  };
  return <>
    <ProForm<ConnectionDraft> form={form} initialValues={{ ...config, api_key: '' }} layout="vertical" requiredMark={false}
      onValuesChange={changed => { revision.current += 1; setResult(undefined); if ('base_url' in changed || 'api_key' in changed) { setModels([]); setCatalogNote(undefined); } }}
      submitter={{ searchConfig: { submitText: '保存连接' }, resetButtonProps: false, submitButtonProps: { disabled: Boolean(busy) } }}
      onFinish={async values => { try { await send('/ai/connection', values, 'PUT'); form.setFieldValue('api_key', ''); await onSaved(); void message.success('模型连接已保存'); return true; } catch (error) { void message.error(errorMessage(error)); return false; } }}>
      <ProFormText name="base_url" label="API 地址" placeholder="https://api.example.com/v1" rules={[{ required: true }, { type: 'url' }]} extra="填写 OpenAI 兼容地址；火山 Coding Plan 的 /api/coding 会自动补全为 /api/coding/v3。" />
      <Form.Item name="model" label="模型名称" rules={[{ required: true, message: '请填写模型名称' }, { max: 120 }]} extra="可获取目录后选择，也可直接输入供应商提供的模型 ID。">
        <AutoComplete options={models.map(value => ({ value }))} placeholder="供应商提供的模型 ID" filterOption={(input, option) => String(option?.value || '').toLowerCase().includes(input.toLowerCase())} />
      </Form.Item>
      <ProFormText.Password name="api_key" label="API 密钥" placeholder={config.has_key ? '已保存密钥；同一地址留空保持原值' : '输入 API 密钥'} fieldProps={{ autoComplete: 'new-password' }} extra="密钥加密保存在服务端；更换地址时需重新填写。本地无鉴权模型可填 local-model。" />
      <ProFormSelect name="output_mode" label="结构化输出方式" options={[{ label: 'JSON 模式（推荐用于兼容接口）', value: 'json' }, { label: 'JSON Schema（供应商支持时）', value: 'structured' }]} rules={[{ required: true }]} />
      <ProFormDigit name="timeout_seconds" label="请求超时（秒）" min={10} max={180} rules={[{ required: true }]} /><ProFormSwitch name="enabled" label="启用模型连接" />
    </ProForm>
    <div className="connection-test"><Space wrap>
      <Button icon={<ApiOutlined />} loading={busy === 'models'} disabled={Boolean(busy && busy !== 'models')} onClick={() => void request('models')}>获取模型</Button>
      <Button icon={<CheckCircleOutlined />} loading={busy === 'test'} disabled={Boolean(busy && busy !== 'test')} onClick={() => void request('test')}>测试连接</Button>
    </Space><p className="muted small">使用当前填写的配置，测试会执行一次真实模型请求。确认可用后保存；未启用也可测试。</p>
      {catalogNote && <Alert showIcon type="info" message={catalogNote} className="form-alert" />}
      {result && <Alert showIcon type={result.ok ? 'success' : 'error'} message={result.text} />}
    </div>
  </>;
}
function SkillEditor({ skill, onClose, onSaved }: { skill?: Skill | 'new'; onClose: () => void; onSaved: () => Promise<void> }) {
  const formId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const existing = skill && skill !== 'new' ? skill : undefined;
  return <StableModal title={existing ? `编辑 ${existing.title} · 保存为 v${existing.version + 1}` : '新增 skill'} open={Boolean(skill)} width={860} onCancel={onClose} afterClose={() => setError(undefined)}
    footer={<Space><Button onClick={onClose}>取消</Button><Button type="primary" htmlType="submit" form={formId} loading={busy}>保存版本</Button></Space>}>
    <p className="muted">标准 SKILL.md 包含 YAML frontmatter 和 Markdown 指令。frontmatter 中的 name 应与 skill 名称一致。</p>{error && <Alert type="error" showIcon message={error} className="form-alert" />}
    <Form id={formId} layout="vertical" scrollToFirstError={{ block: 'center' }} initialValues={existing || { markdown: '---\nname: your-skill\ndescription: 描述何时使用这个能力\n---\n\n# 助教指令\n\n说明目标、判断依据、回应方式和限制。\n' }} onFinish={async (values: { slug: string; title: string; markdown: string }) => { setBusy(true); setError(undefined); try { await send(`/ai/skills/${values.slug}`, values, 'PUT'); await onSaved(); } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); } }}>
      <div className="form-grid"><Form.Item name="title" label="显示标题" rules={[{ required: true }, { max: 80 }]}><Input /></Form.Item><Form.Item name="slug" label="skill 名称" rules={[{ required: true }, { max: 64 }, { pattern: /^[a-z0-9]+(?:-[a-z0-9]+)*$/, message: '仅使用小写字母、数字和连字符' }]}><Input disabled={Boolean(existing)} placeholder="your-skill" /></Form.Item></div>
      <Form.Item name="markdown" label="SKILL.md" rules={[{ required: true }, { min: 20, max: 30000 }]}><Input.TextArea className="code-editor" rows={12} spellCheck={false} /></Form.Item>
    </Form>
  </StableModal>;
}
