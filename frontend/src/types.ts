export type Role = 'teacher' | 'student';
export interface User { id: string; name: string; username: string; role: Role }
export interface Stage { name: string; minutes: number }
export interface RuleSettings {
  enabled: boolean; mode: 'automatic' | 'approval' | 'notify'; window_seconds: number;
  cooldown_seconds: number; persistent_count: number; silence_seconds: number; min_messages: number;
  bindings: Record<string, string>;
}
export interface TopicSettings {
  grouping_mode: 'manual' | 'random' | 'self'; group_size: number; stages: Stage[]; rules?: RuleSettings;
}
export interface Topic {
  id: string; title: string; description: string; references?: string; join_code: string; join_open: boolean;
  status: 'preparing' | 'active' | 'completed'; settings: TopicSettings; config_version: number;
  created_at: number; student_count: number; group_count: number; online_count: number; is_demo: boolean;
}
export interface Member { id: string; name: string; online: boolean; group_id?: string | null }
export interface StudentMetrics {
  user_id: string; name: string; NS: number; total_messages: number; Max_TS: number | null;
  silence_seconds: number | null; last_activity: number | null;
  cognitive: Record<string, number>; emotion: Record<string, number>;
}
export interface Metrics {
  NA: number; NS: number; Max_TS: number | null; TC: boolean; SD: number | null; SR: number | null;
  SE: number | null; SC: null; member_count: number; total_messages: number; pending_messages: number;
  failed_messages: number; last_analyzed_at: number | null; coverage: number | null;
  cognitive: Record<string, number>; emotion: Record<string, number>; social: Record<string, number>;
  metacognitive: Record<string, number>;
  students: StudentMetrics[]; edges: { source: string; target: string }[];
  window_start: number; window_end: number; phase_id: string | null;
  analysis_state: 'ready' | 'failed' | 'pending' | 'observing';
}
export interface Concern { rule: string; reason: string }
export interface AssistantOverview {
  status: string; model_status: 'ready' | 'disabled' | 'unconfigured'; model: string | null;
  connection_version: number | null; rules_enabled: boolean; mode: string; window_seconds: number;
  cooldown_seconds: number; analysis_pending: number; analysis_running: number; analysis_blocked: number;
  analysis_failed: number; retrying: number; generating: number; pending_approval: number;
  notifications: number; generation_failed: number; published: number; cooldown_until: number | null;
  review_pending: number; review_waiting_data: number; next_review_at: number | null; updated_at: number;
}
export interface Group {
  id: string; topic_id: string; name: string; direction: string; capacity: number; member_count: number;
  online_count: number; state: 'waiting' | 'active' | 'paused' | 'completed'; phase_index: number;
  version: number; phase_id: string | null; deadline: number | null; remaining_seconds: number | null;
  members?: Member[]; metrics?: Metrics; concerns?: Concern[]; intervention_state?: string;
  assistant?: AssistantOverview;
}
export interface MeaningUnit {
  id: string; message_id: string; start: number; end: number; quote: string; cognitive: string; emotion: string;
  task_relevant: boolean; metacognitive: string[]; social: string[]; reason: string; confidence: number;
  skill_slug: string; skill_version: number; config_version: number; model: string; corrected: boolean;
  created_at: number;
}
export interface ChatMessage {
  id: string; group_id: string; phase_id: string | null; author_id: string | null; author_name: string;
  kind: 'student' | 'teacher' | 'ai'; content: string; reply_to: string | null;
  analysis_status: string; created_at: number; units?: MeaningUnit[];
}
export interface Outcome { id: string; phase_id: string; author_id: string; content: string; created_at: number }
export interface Intervention {
  id: string; group_id: string; phase_id: string; rule: string; skill_slug: string; skill_version: number;
  config_version: number; model: string; mode: string; status: string; content: string;
  evidence: { reason: string; message_ids?: string[]; agent_rationale?: string; metrics?: Metrics };
  target_user_id: string | null; published_at: number | null; review_at: number | null;
  effect: { result: string; note?: string; observed_messages?: number; required_messages?: number } | null; created_at: number;
}
export interface AuditEvent { id: string; group_id: string | null; event: string; data: Record<string, unknown>; created_at: number }
export interface TopicDetail extends Topic {
  references: string; teacher_name: string; groups: Group[]; my_group_id: string | null;
  students?: Member[]; interventions?: Intervention[]; events?: AuditEvent[]; start_blocked_reason?: string | null;
}
export interface GroupDetail extends Group {
  topic_title: string; stages: Stage[]; instructions: string; references: string;
  members: Member[]; messages: ChatMessage[]; message_count: number; outcomes: Outcome[]; start_blocked_reason?: string | null;
  interventions?: Intervention[]; snapshots?: { id: string; window_start: number; window_end: number; data: Metrics; created_at: number }[];
  jobs?: AnalysisTask[];
}
export interface AnalysisTask {
  id: string; phase_id: string; kind: string; status: string; attempts: number; error: string | null;
  created_at: number; available_at: number; intervention_id: string | null; model: string | null;
  connection_version: number | null; skill_slug: string | null; skill_version: number | null;
  config_version: number | null;
}
export interface Skill {
  id: string; slug: string; title: string; description: string; version: number; markdown: string; digest: string; created_at: number;
}
export interface ExampleSummary {
  id: string; title: string; description: string; recorded_at: number; source_note: string;
  model: string; student_count: number; group_count: number; message_count: number;
  unit_count: number; checkpoint_count: number;
}
export interface ClassroomExample extends Omit<ExampleSummary, 'group_count' | 'message_count' | 'unit_count' | 'checkpoint_count'> {
  settings: TopicSettings;
  analysis_runs: Record<string, unknown>[];
  groups: GroupDetail[];
  checkpoints: { id: string; label: string; captured_at: number; group: GroupDetail }[];
  events: AuditEvent[];
  phases: { id: string; group_id: string; index: number; name: string; started_at: number; ended_at: number | null }[];
  skills: Skill[];
  checks: { label: string; result: string; detail: string; at: number }[];
  provenance: { source_sha256: string; method: string };
}
export interface Connection {
  base_url: string; model: string; has_key: boolean; output_mode: 'json' | 'structured'; timeout_seconds: number;
  enabled: boolean; version: number; framework: string;
}
export interface GroupPlanItem { name: string; direction: string; capacity: number; member_ids: string[] }
export interface GroupPlan { enrollment_ids: string[]; groups: GroupPlanItem[] }
export interface Presentation {
  id: string; title: string; status: string; stages: Stage[]; student_count: number;
  groups: { name: string; state: Group['state']; phase_index: number; deadline: number | null;
    online_count: number; support_status: string; pending_prompts: number;
    metrics: Pick<Metrics, 'NA' | 'NS' | 'TC' | 'SD' | 'SR' | 'SE' | 'member_count' |
      'total_messages' | 'pending_messages' | 'failed_messages' | 'analysis_state' | 'last_analyzed_at' | 'coverage' | 'cognitive'> }[];
}
