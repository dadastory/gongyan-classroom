import type { RuleSettings, TopicSettings } from './types';

export const DEFAULT_RULES: RuleSettings = {
  enabled: false, mode: 'approval', window_seconds: 180, cooldown_seconds: 180, persistent_count: 3,
  silence_seconds: 120, min_messages: 4,
  bindings: { 'persistent-confusion': 'cognitive-clarification', 'persistent-negative': 'emotional-support',
    'low-participation': 'participation-invitation', 'unbalanced-interaction': 'collaboration-coordination',
    'off-topic': 'task-refocus' },
};
export const DEFAULT_SETTINGS: TopicSettings = {
  grouping_mode: 'random', group_size: 6, stages: [
    { name: '观点表达', minutes: 8 }, { name: '问题探索', minutes: 10 },
    { name: '论证协商', minutes: 12 }, { name: '共同总结', minutes: 8 },
  ], rules: DEFAULT_RULES,
};
export const STATE_NAMES: Record<string, string> = { waiting: '等待开始', active: '正在讨论', paused: '已暂停', completed: '已完成', preparing: '准备中' };
export const STATE_COLORS: Record<string, string> = { waiting: 'default', active: 'processing', paused: 'warning', completed: 'success', preparing: 'default' };
export const RULE_NAMES: Record<string, string> = { 'persistent-confusion': '持续困惑', 'persistent-negative': '持续挫败',
  'low-participation': '参与不足', 'unbalanced-interaction': '互动失衡', 'off-topic': '偏离任务', summary: '阶段总结' };
export const COGNITIVE_NAMES = ['非任务话语', '观点表达', '问题探索', '解释论证', '共同建构', '应用反思'];
export const EMOTION_NAMES: Record<string, string> = { E0: '中立', E1: '积极', E2: '困惑', E3: '消极' };
export const SUPPORT_NAMES: Record<string, string> = { waiting: '等待讨论', paused: '讨论暂停', completed: '讨论完成',
  'model-unconfigured': '待配置模型', 'model-disabled': '模型未启用', generating: '生成提示中', analyzing: '编码处理中',
  'needs-teacher': '待老师处理', queued: '编码排队中', failed: '有任务失败', cooldown: '干预冷却中',
  manual: '仅手动支架', monitoring: '持续观察中' };
export const RULE_MODE_NAMES: Record<string, string> = { automatic: '自动发布', approval: '教师确认', notify: '仅提醒老师' };
export const METACOGNITIVE_NAMES: Record<string, string> = { M1: '计划与分工', M2: '监控与评价', M3: '调整策略' };
export const SOCIAL_NAMES: Record<string, string> = { SS1: '邀请参与', SS2: '请求帮助', SS3: '提供帮助', SS4: '协调分工', SS5: '鼓励同伴' };
export const INTERVENTION_NAMES: Record<string, string> = { generating: '生成中', pending: '待老师确认', notify: '提醒老师',
  published: '已发布', dismissed: '已忽略', stale: '已过期', failed: '生成失败' };
export const EVENT_NAMES: Record<string, string> = { 'group.start': '开始讨论', 'group.pause': '暂停讨论', 'group.resume': '恢复讨论',
  'group.advance': '推进阶段', 'group.complete': '完成讨论', 'student.joined': '学生加入', 'topic.created': '创建课题',
  'topic.updated': '更新课题设置', 'groups.randomized': '应用随机分组', 'group.created': '创建小组',
  'group.assigned': '调整分组', 'group.self-joined': '学生选择小组', 'outcome.submitted': '提交阶段成果',
  'group.removed': '移除准备阶段小组', 'analysis.attempt_failed': '模型分析或提示生成失败',
  'unit.corrected': '人工修正编码', 'intervention.requested': '请求智能提示', 'intervention.published': '发布智能提示',
  'intervention.dismissed': '忽略智能提示', 'student.removed': '移除课题成员' };
export const timeText = (timestamp?: number | null) => timestamp ? new Date(timestamp * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '暂无';
export const durationText = (seconds: number | null | undefined) => seconds == null ? '暂无数据' : seconds < 60 ? `${Math.round(seconds)} 秒` : `${Math.floor(seconds / 60)} 分 ${Math.round(seconds % 60)} 秒`;
