/**
 * Shared types for the UnBubble console.
 *
 * Everything here is DERIVED from the files the three skills write into
 * ~/UnBubble-Projects/<app-id>/ — the files are the source of truth. The only
 * UI-owned state is `ProjectState` (persisted as <app>/unbubble.json).
 */

export type StageStatus = 'not_started' | 'in_progress' | 'done';

export type StageKey = 'audit' | 'clone' | 'levelup_docs' | 'levelup_impl';

export interface StageOverride {
  status?: StageStatus;
  note?: string;
  updated_at?: string;
}

/** <app>/unbubble.json — the only file the UI writes. */
export interface ProjectState {
  version: 1;
  name?: string;
  stages?: Partial<Record<StageKey, StageOverride>>;
  stories_done?: string[];
  links?: {
    rebuild_repo?: string;
    github?: string;
    tracker?: string;
    bubble_export?: string;
  };
  notes?: string;
  updated_at?: string;
}

export interface FileInfo {
  path: string; // relative to the project folder
  size: number;
  mtime: string; // ISO
}

// ---------------------------------------------------------------- audit

export type Confidence = 'high' | 'review' | 'destructive';

export interface AuditCategory {
  key: string;
  count: number;
  confidence: Confidence;
  /** Report section id (h2 anchor: p, r, b, o, pl, s, d, w, ap, g) this category is signed off with. */
  section: string;
  /** No findings, or the owner signed the section off in the report (kept items recorded). */
  resolved: boolean;
  /** Items the owner kept on purpose in a signed-off section (from the progress file). */
  kept: KeptItem[];
}

/** An unused entity the owner decided to keep — the clone step asks whether it enters parity. */
export interface KeptItem {
  key: string; // "<category>:<id>" as in the report
  label: string;
  section: string;
}

export interface AuditProgress {
  path: string;
  updated?: string;
  deleted: number;
  sectionsDone: string[];
  kept: KeptItem[];
}

export interface AuditRound {
  version: number | null; // null = file without a -vN suffix
  label: string; // "v3" or "—"
  date: string; // ISO date of the HTML/JSON file
  html?: string; // relative path of the report (pt)
  htmlEn?: string; // relative path of the English report, when present
  json?: string;
  totalFindings: number | null; // null when there is no JSON for this round
  categories: AuditCategory[];
  totals?: {
    pages: number;
    reusables: number;
    backend: number;
    optionSets: number;
    plugins: number;
    styles: number;
    dataTables: number;
    dataFields: number;
    apiCalls: number;
    mobileViews: number;
  };
}

/**
 * audit/cleanup-applied__<app>.json — deletions applied through the connected mode
 * (unbubble:connect cleanup_journal.py). An entry counts as deleted in the app only when the
 * call succeeded and it was applied to `test` itself or to a branch the owner merged.
 */
export interface CleanupJournalSummary {
  path: string;
  updated?: string;
  entries: number;
  /** Count as deleted: applied to test, or on a branch that was merged. */
  applied: number;
  /** Applied on a branch that is not merged (yet) — never counted. */
  pending: number;
  failed: number;
  /** Confirmed gone by a later audit round (cleanup_journal.py verify). */
  verified: number;
  versions: { appVersion: string; applied: number; pending: number; failed: number; verified: number }[];
}

export interface AuditStage {
  status: StageStatus;
  derivedStatus: StageStatus;
  override?: StageOverride;
  rounds: AuditRound[];
  latest?: AuditRound;
  progressFile?: AuditProgress;
  journal?: CleanupJournalSummary;
  sectionsTotal: number;
  /** Sections signed off / sections that still have findings. */
  sectionsResolved: number;
  sectionsWithFindings: number;
  progress: number; // 0..1 — 1 when the latest round has zero findings or every section is signed off
}

// ---------------------------------------------------------------- clone

export interface ChecklistItem {
  key: string;
  label: string;
  done: boolean;
  file?: FileInfo;
  detail?: string;
  optional?: boolean;
}

export interface ParityMatrixSummary {
  file: FileInfo;
  rows: number;
  withDisposition: number;
  blank: number;
  byDisposition: Record<string, number>;
  generatedOn?: string;
}

export interface OpenQuestionsSummary {
  file: FileInfo;
  blocking: number;
  nonBlocking: number;
  decisionDates: string[];
  hasDecisions: boolean;
}

export interface CloneStage {
  status: StageStatus;
  derivedStatus: StageStatus;
  override?: StageOverride;
  items: ChecklistItem[];
  docs: ChecklistItem[]; // the 00..08 set
  extraDocs: FileInfo[]; // 09+ or anything else in docs/
  progress: number;
  summary?: {
    app_domain?: string;
    counts?: Record<string, number>;
    security_flags?: Record<string, string[]>;
    file: FileInfo;
  };
  secrets?: { envPresent: boolean; keysDoc?: FileInfo; envExample?: FileInfo; varCount?: number };
  matrix?: ParityMatrixSummary;
  openQuestions?: OpenQuestionsSummary;
}

// ---------------------------------------------------------------- level-up

export interface SpecCoverageSummary {
  file: FileInfo;
  gate: 'PASS' | 'FAIL' | string;
  coverage_pct: number;
  requirements_total: number;
  requirements_covered: number;
  stories_total: number;
  orphan_stories: number;
  non_atomic_stories: number;
  requirements_missing_acceptance: number;
  unknown_citations: number;
  strict_acceptance: boolean;
}

export interface ParityReportSummary {
  file: FileInfo;
  column_coverage_pct: number;
  tables_total: number;
  tables_orphaned: number;
  columns_considered: number;
  columns_orphaned_high_confidence: number;
  columns_orphaned_low_signal: number;
  app_dir?: string;
}

export interface BacklogStory {
  id: string;
  size?: string;
  epic: string;
  text: string; // first line, markdown stripped
  infra: boolean;
  nonAtomic: boolean;
  cites: string[];
  line: number;
}

export interface BacklogEpic {
  title: string;
  stories: BacklogStory[];
}

export interface LevelUpStage {
  docsStatus: StageStatus;
  docsDerivedStatus: StageStatus;
  docsOverride?: StageOverride;
  docs: ChecklistItem[];
  extraDocs: FileInfo[];
  docsProgress: number;
  specCoverage?: SpecCoverageSummary;
  parityReport?: ParityReportSummary;
  implStatus: StageStatus;
  implDerivedStatus: StageStatus;
  implOverride?: StageOverride;
  backlog?: {
    file: FileInfo;
    epics: BacklogEpic[];
    total: number;
    done: number;
    infra: number;
    nonAtomic: number;
  };
  implProgress: number;
}

// ---------------------------------------------------------------- project

export interface ProjectSummary {
  id: string;
  name: string;
  dir: string;
  updatedAt: string; // most recent artifact mtime
  domain?: string;
  counts?: Record<string, number>;
  stages: {
    audit: { status: StageStatus; progress: number; detail: string };
    clone: { status: StageStatus; progress: number; detail: string };
    levelup_docs: { status: StageStatus; progress: number; detail: string };
    levelup_impl: { status: StageStatus; progress: number; detail: string };
  };
  nextStep: StageKey | 'rebuild_done';
}

export interface ProjectDetail extends ProjectSummary {
  audit: AuditStage;
  clone: CloneStage;
  levelup: LevelUpStage;
  state: ProjectState;
  files: FileInfo[];
  /** Connected mode (unbubble:connect): MCP profiles bound to this app and the newest downloaded export. */
  connection?: ProjectConnection;
}

// ---------------------------------------------------------------- docs

export interface DocEntry {
  path: string; // relative path inside the project folder
  group: string; // group key
  title: string;
  size: number;
  mtime: string;
  kind: 'md' | 'json' | 'html' | 'text';
}

// ---------------------------------------------------------------- setup / install

export type HostKey =
  | 'claude'
  | 'codex'
  | 'agents'
  | 'cursor'
  | 'gemini'
  | 'copilot'
  | 'opencode'
  | 'windsurf';

export type InstallKind = 'symlink' | 'copy' | 'plugin' | 'source';

export interface SkillPresence {
  /** `connect` is optional: "complete" means the three core skills. */
  skill: 'audit' | 'clone' | 'level-up' | 'connect';
  path: string;
  inSync: boolean | null; // null = could not compare
}

export interface InstallLocation {
  path: string;
  kind: InstallKind;
  target?: string; // symlink target
  version?: string; // from .claude-plugin/plugin.json when present
  skills: SkillPresence[];
  complete: boolean; // the three core skills found (connect is optional)
  inSync: boolean | null;
}

export interface HostInstall {
  host: HostKey;
  label: string;
  vendor: string;
  detectedOnMachine: boolean; // the host's home dir exists
  roots: string[]; // skill roots we looked at
  locations: InstallLocation[];
  status: 'installed' | 'partial' | 'not_installed' | 'host_absent';
}

export interface SetupInfo {
  repoDir: string;
  repoIsValid: boolean;
  repoVersion?: string;
  projectsDir: string;
  projectsDirExists: boolean;
  projectCount: number;
  home: string;
  hosts: HostInstall[];
  scannedAt: string;
}

// ---------------------------------------------------------------- connected mode (unbubble:connect)

/** An MCP profile as `mcp/launch.py doctor` reports it — session existence and date only, never content. */
export interface ConnectedProfile {
  name: string;
  appId: string | null;
  appVersion: string | null;
  /** A branch profile reuses its app's session. */
  sessionProfile: string | null;
  sessionCaptured: boolean;
  sessionUpdated: string | null;
  /** Roles with a captured test-user session for logged-in screen captures (names only). */
  appSessions: string[];
  rebuildSessions: string[];
}

/** Provenance sidecar of an export downloaded by fetch_export.py (`<export>.meta.json`). */
export interface ExportProvenance {
  file: string;
  appVersion: string | null;
  fetchedAt: string | null;
  sha256: string | null;
  bytes: number | null;
}

export interface ConnectedModeInfo {
  /** mcp/launch.py exists in the repository. */
  available: boolean;
  /** Every doctor check passed. */
  installed: boolean;
  error?: string;
  launcher: string;
  home: string;
  vendored?: { commit: string; ref: string; files: number };
  checks: { name: string; ok: boolean; detail: string }[];
  /** Agent hosts where the MCP server is registered. */
  hosts: Record<string, boolean>;
  profiles: ConnectedProfile[];
  exports: Record<string, { count: number; latest: ExportProvenance }>;
  /** One browser sign-in shared by every profile; candidates that may already be signed in. */
  browsers: { shared: boolean; profiles: string[]; importable: string[] };
}

export interface ProjectConnection {
  profiles: ConnectedProfile[];
  latestExport?: ExportProvenance;
  exportCount: number;
}
