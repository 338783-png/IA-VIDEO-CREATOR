// Client typé pour le backend FastAPI.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type TargetFormat = "tiktok" | "reels" | "shorts" | "youtube";

export interface Project {
  id: number;
  name: string;
  description: string;
  instruction: string;
  target_format: TargetFormat;
  project_type: "2d" | "3d";
  status: string;
  settings: Record<string, unknown>;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectCard extends Project {
  thumbnail_media_id: number | null; media_count: number; storyboard_version: number | null;
  storyboard_status: "draft" | "validated" | null; exports_count: number;
}

export interface ExportRow {
  id: number; project_id: number; project_name: string | null; platform: string; path: string; file_exists: boolean;
  size_bytes: number | null; settings: { quality?: string; fps?: number }; verification: { ok?: boolean; checks?: Record<string, boolean> };
  storyboard_version: number; created_at: string; ok: boolean | undefined; subtitle_files: string[];
}

export interface StoryboardRow {
  project_id: number; project_name: string; project_type: "2d" | "3d"; version: number; status: "draft" | "validated";
  scenes: number; duration: number | null; platform: string | null; style: string | null; has_preview: boolean; updated_at: string;
}

export interface Media {
  id: number;
  project_id: number | null;
  kind: "video" | "audio" | "image" | "reference" | "script";
  category: "video" | "audio" | "image" | "script";
  original_name: string;
  stored_path: string;
  size_bytes: number;
  probe: {
    duration?: number | null;
    video?: { codec: string; width: number; height: number; fps: number | null } | null;
    audio?: { codec: string; sample_rate: string; channels: number } | null;
  };
  created_at: string;
}

export interface ProjectDetail extends Project {
  media: Media[];
}

export interface SystemStatus {
  platform: string;
  python: string;
  database: { ok: boolean; url: string };
  ffmpeg: { available: boolean; ffmpeg: string | null; ffprobe: string | null };
  ollama: { available: boolean; url: string; models: string[]; configured_model: string; model_ready: boolean };
  disk_free_gb: number;
  limits_mb: { video: number; audio: number; image: number };
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "network", "Backend injoignable. Lancez scripts/start.ps1 (ou start.sh).");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : Array.isArray(body.detail) ? body.detail.map((d: { msg: string }) => d.msg).join(", ") : res.statusText;
    throw new ApiError(res.status, body.error ?? "http_error", detail);
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  systemStatus: () => request<SystemStatus>("/api/system/status"),
  listProjects: () => request<ProjectCard[]>("/api/projects"),
  listExports: (params: { project_id?: number; platform?: string; limit?: number } = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]));
    return request<ExportRow[]>(`/api/exports?${q}`);
  },
  listStoryboards: () => request<StoryboardRow[]>("/api/storyboards"),
  exportFileUrl: (id: number) => `${API_URL}/api/exports/${id}/file`,
  getProject: (id: number) => request<ProjectDetail>(`/api/projects/${id}`),
  createProject: (data: Pick<Project, "name"> & Partial<Pick<Project, "description" | "instruction" | "target_format" | "project_type">>) =>
    request<Project>("/api/projects", json("POST", data)),
  updateProject: (id: number, data: Partial<Project>) => request<Project>(`/api/projects/${id}`, json("PATCH", data)),
  archiveProject: (id: number) => request<Project>(`/api/projects/${id}`, { method: "DELETE" }),
  listMedia: (params: { project_id?: number; kind?: string } = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]));
    return request<Media[]>(`/api/media?${q}`);
  },
  upload: (files: File[], kind: Media["kind"], projectId?: number) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("kind", kind);
    if (projectId !== undefined) fd.append("project_id", String(projectId));
    return request<Media[]>("/api/media/upload", { method: "POST", body: fd });
  },
  mediaUrl: (id: number) => `${API_URL}/api/media/${id}/file`,
  thumbnailUrl: (id: number) => `${API_URL}/api/media/${id}/thumbnail`,
};

export const ACCEPT = {
  video: ".mp4,.mov,.avi",
  script: ".txt,.md,.srt",
  audio: ".mp3,.wav",
  image: ".png,.jpg,.jpeg",
  reference: ".mp4,.mov,.avi",
} as const;

// ---------------------------------------------------------------- Prompt 2 : références et styles
export interface Job {
  id: number;
  type: string;
  target_id: number | null;
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted";
  progress: number;
  message: string;
  error: string;
  result: Record<string, unknown>;
}

export interface ReferenceItem {
  id: number;
  original_name: string;
  size_bytes: number;
  probe: Media["probe"];
  created_at: string;
  analyzed: boolean;
  analyzed_at: string | null;
  summary: { shots: number; pace: string; aspect: string; captions: boolean; bpm: number | null } | null;
  last_job: Job | null;
}

export interface Motion {
  type: string;
  zoom_total?: number;
  zoom_per_second?: number;
  pan?: [number, number];
  confidence: string;
}

export interface Scene {
  index: number;
  start: number;
  end: number;
  duration: number;
  transition_in: { type: string; duration: number; confidence: string } | null;
  motion: Motion;
  palette: { hex: string; share: number }[];
  keyframe: string;
}

export interface Analysis {
  format: { width: number; height: number; aspect: string; fps: number; duration: number; orientation: string; video_codec: string; audio_codec: string | null };
  rhythm: { shot_count: number; avg_shot: number; median_shot: number; min_shot: number; max_shot: number; cuts_per_minute: number | null; pace: string; trend: string | null };
  transitions: { counts: Record<string, number>; total: number; avg_gradual_duration: number | null };
  motion: { counts: Record<string, number>; zoom_share: number };
  colors: { palette: { hex: string; share: number }[]; stats: Record<string, number | string>; description: string[] };
  captions: {
    detected: boolean; position?: string; vertical_center_pct?: number; fill_color?: string | null; outline_color?: string | null;
    change_interval_s?: number | null; mode?: string; coverage?: number; confidence: string; font_note?: string; reason?: string;
  };
  audio: {
    has_audio: boolean; loudness_lufs?: number | null; tempo_bpm?: number | null; tempo_confidence?: number; silence_ratio?: number;
    music?: { likely: boolean; description: string; confidence: string };
    sync?: { cuts: number; cuts_on_onset_ratio: number | null; cuts_on_beat_ratio: number | null };
    sound_effects?: { on_cuts_ratio: number | null; description: string };
  };
  vision: { available: boolean; model?: string; note?: string; frames?: Record<string, unknown>[] };
  scenes: Scene[];
  limits: string[];
}

export interface StyleRule { key: string; label: string; value: string; source: string; confidence: string }

export interface StyleListItem {
  id: number; name: string; status: "draft" | "validated" | "rejected"; is_official: boolean;
  reference_media_ids: number[]; validated_at: string | null; updated_at: string;
}

export interface StyleConfig {
  format: { aspect: string; width: number; height: number; fps: number };
  rhythm: { target_shot_duration: number; min_shot: number; max_shot: number; pace: string };
  transitions: { default: string; distribution: Record<string, number>; durations: Record<string, number> };
  motion: { zoom: { enabled: boolean; probability: number; direction: "in" | "out"; scale_per_second: number; max_scale: number }; pan: { enabled: boolean } };
  color: { palette: { hex: string; share: number }[]; grading: Record<string, number | string> };
  subtitles: {
    enabled: boolean; position?: string; primary_color?: string; outline_color?: string; outline?: boolean; mode?: string;
    font: { family: string | null; suggestions: string[]; note?: string }; confidence: string;
  };
  audio: { has_reference_audio: boolean; music?: { enabled: boolean; bpm: number | null }; target_lufs?: number; sfx_on_cuts?: boolean };
  sync: { cut_on_beat: boolean; tolerance_ms: number; subtitle_sync: string };
  [k: string]: unknown;
}

export interface Style extends StyleListItem {
  summary: { mandatory: StyleRule[]; optional: StyleRule[]; per_scene: Record<string, string | number>[]; limits: string[]; reference_count: number; scene_count: number };
  config: StyleConfig;
  markdown: string;
  user_notes: string;
  files_dir: string;
}

export const refApi = {
  list: () => request<ReferenceItem[]>("/api/references"),
  analyze: (id: number) => request<Job>(`/api/references/${id}/analyze`, { method: "POST" }),
  analysis: (id: number) => request<Analysis>(`/api/references/${id}/analysis`),
  keyframeUrl: (id: number, name: string) => `${API_URL}/api/references/${id}/keyframes/${name}`,
  job: (id: number) => request<Job>(`/api/jobs/${id}`),
  cancelJob: (id: number) => request<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),
};

export const styleApi = {
  list: () => request<StyleListItem[]>("/api/styles"),
  get: (id: number) => request<Style>(`/api/styles/${id}`),
  create: (name: string, reference_media_ids: number[]) => request<Style>("/api/styles", json("POST", { name, reference_media_ids })),
  update: (id: number, body: { name?: string; user_notes?: string; config_patch?: Record<string, unknown> }) =>
    request<Style>(`/api/styles/${id}`, json("PATCH", body)),
  validate: (id: number) => request<Style>(`/api/styles/${id}/validate`, { method: "POST" }),
  reject: (id: number) => request<Style>(`/api/styles/${id}/reject`, { method: "POST" }),
};

export const LABELS: Record<string, string> = {
  cut: "Coupe franche", crossfade: "Fondu enchaîné", fade_black: "Fondu au noir", flash_white: "Flash blanc",
  animated: "Transition animée", statique: "Plan fixe", zoom_avant: "Zoom avant", zoom_arriere: "Zoom arrière",
  panoramique: "Panoramique", tremblement: "Tremblement", mouvement_interne: "Mouvement interne", trop_court: "Trop court",
};

// ---------------------------------------------------------------- Prompt 3 : moteur de montage
export interface SbWord { word: string; start: number; end: number }
export interface SbScene {
  id: string; position: number; media_id: number; source: string; kind: "video" | "image";
  start: number; end: number; duration: number; timeline_start?: number;
  text: string; text_auto: boolean; words: SbWord[];
  effect: string; transition: string; transition_duration: number; volume: number;
  reason?: string; score?: number | null; group?: number | null;
}
export interface SbSubtitles {
  enabled: boolean; mode: "word" | "chunk" | "phrase"; position: "haut" | "centre" | "bas"; font: string;
  primary_color: string; outline_color: string; highlight_color: string; outline: boolean; uppercase: boolean;
  size_pct: number; animated: boolean; vertical_center_pct?: number; source?: "scenes" | "voiceover"; manual_cues?: Cue[] | null;
}
export interface SbAudio {
  original_volume: number; music_media_id: number | null; music_source?: string | null; music_volume_db: number; ducking: boolean;
  voiceover_media_id: number | null; voiceover: { requested: boolean; status: string; script: string | null }; target_lufs: number;
}
export interface StoryboardData {
  version: number; instruction: string; parsed_instruction: Record<string, unknown>;
  style: { id: number | null; name: string }; format: { platform: TargetFormat; width: number; height: number; fps: number };
  fit_mode: "cover" | "blur"; target_duration: number; total_duration: number;
  scenes: SbScene[]; subtitles: SbSubtitles; audio: SbAudio;
  rejected: { media_id: number; source: string; start: number; end: number; text: string; reason: string }[];
  notes: string[]; llm: { used: boolean; note?: string; title?: string; hook?: string; reason?: string };
}
export interface StoryboardOut { id: number; project_id: number; version: number; status: "draft" | "validated"; data: StoryboardData; has_preview: boolean }
export interface MediaAnalysisItem {
  media: { id: number; kind: string; category: string; original_name: string };
  analyzed: boolean;
  data: { duration?: number; shots?: { start: number; end: number }[]; silences?: number[][]; speech_seconds?: number; tempo_bpm?: number | null; transcription_note?: string };
  transcript: { text: string; language: string; segments: { start: number; end: number; text: string }[] } | null;
}
export interface ExportItem {
  id: number; platform: string; path: string; settings: { quality: string; fps: number };
  verification: { ok: boolean; checks: Record<string, boolean>; warnings: string[] }; storyboard_version: number; created_at: string;
}
export interface EngineStatus {
  ffmpeg: { available: boolean }; ollama: SystemStatus["ollama"];
  whisper: { library: boolean; model: string; downloaded: boolean; approx_size_mb: number };
}

export const editApi = {
  engine: () => request<EngineStatus>("/api/engine/status"),
  analyze: (pid: number, force = false) => request<Job>(`/api/projects/${pid}/analyze`, json("POST", { force, transcribe: true, language: "fr" })),
  analysis: (pid: number) => request<MediaAnalysisItem[]>(`/api/projects/${pid}/analysis`),
  generate: (pid: number, body: { instruction?: string; style_id?: number | null; target_duration?: number | null; platform?: string | null; use_llm?: boolean }) =>
    request<Job>(`/api/projects/${pid}/storyboard/generate`, json("POST", body)),
  storyboard: (pid: number) => request<StoryboardOut>(`/api/projects/${pid}/storyboard`),
  save: (pid: number, body: Partial<StoryboardData> & { base_version: number }) => request<StoryboardOut>(`/api/projects/${pid}/storyboard`, json("PUT", body)),
  preview: (pid: number) => request<Job>(`/api/projects/${pid}/storyboard/preview`, { method: "POST" }),
  previewUrl: (pid: number, version: number) => `${API_URL}/api/projects/${pid}/preview.mp4?version=${version}`,
  validate: (pid: number, version: number) => request<StoryboardOut>(`/api/projects/${pid}/storyboard/validate`, json("POST", { version })),
  exportVideo: (pid: number, body: { platform: string; quality: string; fps: number }) =>
    request<Job>(`/api/projects/${pid}/export`, json("POST", { ...body, confirm: true })),
  exports: (pid: number) => request<ExportItem[]>(`/api/projects/${pid}/exports`),
  exportUrl: (id: number) => `${API_URL}/api/exports/${id}/file`,
  job: (id: number) => request<Job>(`/api/jobs/${id}`),
  cancel: (id: number) => request<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),
};

export const EFFECTS: Record<string, string> = {
  none: "Aucun", zoom_in: "Zoom avant", zoom_out: "Zoom arrière", punch_in: "Recadrage serré", pan_left: "Panoramique ←", pan_right: "Panoramique →",
};
export const TRANSITIONS: Record<string, string> = {
  cut: "Coupe franche", crossfade: "Fondu enchaîné", fade_black: "Fondu au noir", flash_white: "Flash blanc",
  slide_left: "Glissement ←", slide_up: "Glissement ↑", wipe_left: "Balayage", zoom_in: "Zoom", circle_open: "Cercle",
};

// ---------------------------------------------------------------- Prompt 6 : voix off
export interface VoiceInfo {
  id: string; name: string; quality: string | null; language: string; sample_rate: number;
  speakers: { id: string; index: number }[]; license: string | null; source: string | null; excluded: boolean; attribution: string;
}
export interface VoiceParams { voice_id: string; speaker?: string | null; speed: number; pause_s: number; volume_db: number }
export interface VoiceTrackItem { media_id: number; name: string; text: string; voice_id: string; speaker: string | null; params: VoiceParams; duration: number | null }

export const voiceApi = {
  list: () => request<{ installed: boolean; voices: VoiceInfo[] }>("/api/voices"),
  preview: async (body: VoiceParams & { text: string }): Promise<string> => {
    const res = await fetch(`${API_URL}/api/voices/preview`, json("POST", body));
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new ApiError(res.status, b.error ?? "http_error", typeof b.detail === "string" ? b.detail : "Échec de l'écoute");
    }
    return URL.createObjectURL(await res.blob());
  },
  generate: (pid: number, body: VoiceParams & { text: string; name?: string }) => request<Job>(`/api/projects/${pid}/voiceover`, json("POST", body)),
  tracks: (pid: number) => request<VoiceTrackItem[]>(`/api/projects/${pid}/voice-tracks`),
};

// ---------------------------------------------------------------- Prompt 5 : sous-titres
export interface Cue { start: number; end: number; text: string }
export interface SubtitlesOut { version: number; manual: boolean; cues: Cue[]; sync: { checked: number; max_offset_ms: number | null; ok: boolean } }
export const subApi = {
  get: (pid: number) => request<SubtitlesOut>(`/api/projects/${pid}/subtitles`),
  fileUrl: (pid: number, fmt: "srt" | "vtt") => `${API_URL}/api/projects/${pid}/subtitles?format=${fmt}`,
};

// ---------------------------------------------------------------- Module 2D.1 : personnages et scénarios
export interface CharacterVoice { voice_id: string; speaker?: string | null; speed: number }
export interface Character {
  id: number; name: string; kind: "2d" | "3d"; description: string; appearance: Record<string, unknown>;
  voice: CharacterVoice | Record<string, never>; settings: Record<string, unknown>; updated_at: string;
}
export interface ScLine { id?: string; character_id: number; text: string; emotion: string; intention: string; pause_after: number; estimated_seconds?: number }
export interface ScScene { id?: string; title: string; setting: string; camera: string; lines: ScLine[] }
export interface ScenarioData { title: string; topic: string; scenes: ScScene[]; estimated_seconds?: number; lines_count?: number; generated?: boolean }
export interface ScenarioOut { id: number; version: number; status: "draft" | "validated"; data: ScenarioData }
export const EMOTIONS = ["neutre", "joyeux", "enthousiaste", "surpris", "pensif", "triste", "inquiet", "en colère"];
export const CAMERAS: Record<string, string> = {
  plan_moyen: "Plan moyen", plan_rapproche: "Plan rapproché", plan_large: "Plan large", zoom_avant: "Zoom avant", zoom_arriere: "Zoom arrière", panoramique: "Panoramique",
};

export const charApi = {
  list: (kind?: string) => request<Character[]>(`/api/characters${kind ? `?kind=${kind}` : ""}`),
  create: (b: Partial<Character> & { name: string }) => request<Character>("/api/characters", json("POST", b)),
  update: (id: number, b: Partial<Character>) => request<Character>(`/api/characters/${id}`, json("PATCH", b)),
  duplicate: (id: number) => request<Character>(`/api/characters/${id}/duplicate`, { method: "POST" }),
  remove: (id: number) => request<{ archived: boolean }>(`/api/characters/${id}`, { method: "DELETE" }),
  scenario: (pid: number) => request<ScenarioOut>(`/api/projects/${pid}/scenario`),
  generate: (pid: number, b: { topic: string; character_ids: number[]; target_seconds: number; tone: string; instructions: string }) =>
    request<Job>(`/api/projects/${pid}/scenario/generate`, json("POST", b)),
  save: (pid: number, b: ScenarioData & { base_version?: number }) => request<ScenarioOut>(`/api/projects/${pid}/scenario`, json("PUT", b)),
  validate: (pid: number, version: number) => request<ScenarioOut>(`/api/projects/${pid}/scenario/validate`, json("POST", { version })),
};
