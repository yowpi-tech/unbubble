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

export interface AuditStage {
  status: StageStatus;
  derivedStatus: StageStatus;
  override?: StageOverride;
  rounds: AuditRound[];
  latest?: AuditRound;
  progressFile?: { path: string; deleted: number };
  progress: number; // 0..1 — 1 when the latest round has zero findings
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
  skill: 'audit' | 'clone' | 'level-up';
  path: string;
  inSync: boolean | null; // null = could not compare
}

export interface InstallLocation {
  path: string;
  kind: InstallKind;
  target?: string; // symlink target
  version?: string; // from .claude-plugin/plugin.json when present
  skills: SkillPresence[];
  complete: boolean; // all three skills found
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
