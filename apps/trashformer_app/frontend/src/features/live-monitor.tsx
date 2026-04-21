import React from 'react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { Switch } from '../components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import { cn } from '../lib/utils';
import { invalidateCache, rpcCall } from '../api';
import {
  AlertCircle,
  AlertTriangle,
  Camera,
  CheckCircle2,
  Clock3,
  Cpu,
  Play,
  RefreshCw,
  ScanSearch,
  Square,
} from 'lucide-react';

type ModelStatus = {
  ready: boolean;
  using_mock: boolean;
  mode: string;
  message: string;
  checkpoint_path: string | null;
  checkpoint_sha256: string | null;
  model_name: string | null;
  class_names: string[];
  error: string;
  checked_at_utc: string;
};

type RuntimeCapabilities = {
  host: {
    is_raspberry_pi: boolean;
    pi_model: string;
    platform: string;
  };
  camera_available: boolean;
  camera_reason: string;
  camera_command: string;
  hardware_outputs_available: boolean;
  hardware_outputs_reason: string;
  live_monitor_supported: boolean;
  live_monitor_reason: string;
  checked_at_utc: string;
};

type BoundingBox = {
  left_pct: number;
  top_pct: number;
  width_pct: number;
  height_pct: number;
};

type PresencePayload = {
  has_core_foreground: boolean;
  reference_scene_error: boolean;
  mean_diff: number;
  changed_ratio: number;
  border_mean_diff: number;
  border_changed_ratio: number;
  bbox: BoundingBox | null;
};

type TrackingPayload = {
  stable_for_seconds: number;
  required_hold_seconds: number;
  object_id: string | null;
};

type PredictionPayload = {
  category: string;
  confidence: number;
  model_source: string;
  checkpoint_sha256: string;
  model_name: string;
  inference_time_ms: number;
};

type LiveSnapshot = {
  timestamp_utc: string;
  active: boolean;
  state: string;
  status: string;
  status_message: string;
  error: string;
  image_b64: string;
  image_path: string | null;
  prediction: PredictionPayload | null;
  presence: PresencePayload | null;
  tracking: TrackingPayload;
  decision: 'classified' | 'low_confidence' | null;
  confidence_passed: boolean;
  classification_triggered: boolean;
  classification_event_id: string | null;
  saved_capture_path: string | null;
  hardware: {
    enabled: boolean;
    buzzer_mode: string;
    action: string;
    error: string;
  };
  runtime_capabilities: RuntimeCapabilities;
  model_status: ModelStatus;
  capture_time_ms: number;
};

const HOLD_SECONDS = 2.0;
const POLL_INTERVAL_MS = 1200;
const MIN_CONFIDENCE = 0.6;

function getCategoryLabel(category: string) {
  return category
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function getStatusBadgeClass(status: string) {
  switch (status) {
    case 'initializing':
      return 'bg-violet-500/10 text-violet-400 border-violet-500/20';
    case 'classified':
      return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
    case 'low_confidence':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    case 'tracking':
      return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
    case 'standby':
      return 'bg-slate-500/10 text-slate-300 border-slate-500/20';
    case 'scene_error':
      return 'bg-rose-500/10 text-rose-500 border-rose-500/20';
    case 'degraded':
      return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
    default:
      return 'bg-muted text-muted-foreground';
  }
}

export const LiveMonitor = () => {
  const [running, setRunning] = React.useState(false);
  const [hardwareOutputsEnabled, setHardwareOutputsEnabled] = React.useState(false);
  const [snapshot, setSnapshot] = React.useState<LiveSnapshot | null>(null);
  const [modelStatus, setModelStatus] = React.useState<ModelStatus | null>(null);
  const [runtimeCapabilities, setRuntimeCapabilities] = React.useState<RuntimeCapabilities | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [popupOpen, setPopupOpen] = React.useState(false);
  const [popupPrediction, setPopupPrediction] = React.useState<PredictionPayload | null>(null);
  const timeoutRef = React.useRef<number | null>(null);
  const lastPopupEventIdRef = React.useRef<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    async function loadStatus() {
      try {
        const snapshotData = await rpcCall<LiveSnapshot>({
          func: 'get_runtime_snapshot',
          args: { include_image: false },
          skipCache: true,
        });
        if (!cancelled) {
          setSnapshot(snapshotData);
          setModelStatus(snapshotData.model_status);
          setRuntimeCapabilities(snapshotData.runtime_capabilities);
          setRunning(Boolean(snapshotData.active));
          setError(snapshotData.error || null);
          if (snapshotData.active) {
            setHardwareOutputsEnabled(Boolean(snapshotData.hardware?.enabled));
          } else if (snapshotData.runtime_capabilities.hardware_outputs_available) {
            setHardwareOutputsEnabled(true);
          } else {
            setHardwareOutputsEnabled(false);
          }
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message);
        }
      }
    }

    loadStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (!running) {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      return;
    }

    let cancelled = false;

    async function poll() {
      try {
        const data = await rpcCall<LiveSnapshot>({
          func: 'get_runtime_snapshot',
          args: { include_image: true },
          skipCache: true,
        });

        if (cancelled) {
          return;
        }

        setSnapshot(data);
        setModelStatus(data.model_status);
        setRuntimeCapabilities(data.runtime_capabilities);
        setError(data.error || null);
        setHardwareOutputsEnabled(Boolean(data.hardware?.enabled));
        if (!data.active) {
          setRunning(false);
        }

        if (
          data.classification_triggered &&
          data.confidence_passed &&
          data.prediction &&
          data.classification_event_id &&
          lastPopupEventIdRef.current !== data.classification_event_id
        ) {
          lastPopupEventIdRef.current = data.classification_event_id;
          setPopupPrediction(data.prediction);
          setPopupOpen(true);
          invalidateCache(['get_history', 'get_stats']);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message);
        }
      } finally {
        if (!cancelled) {
          timeoutRef.current = window.setTimeout(poll, POLL_INTERVAL_MS);
        }
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [running]);

  React.useEffect(() => {
    if (!running) {
      return;
    }

    let cancelled = false;

    async function reconfigureRuntime() {
      try {
        const data = await rpcCall<LiveSnapshot>({
          func: 'start_runtime',
          args: {
            stable_hold_seconds: HOLD_SECONDS,
            camera_width: 1280,
            camera_height: 720,
            drive_outputs: hardwareOutputsEnabled,
            standby_reminder_seconds: 20,
            category_hold_seconds: 2.0,
            min_confidence: MIN_CONFIDENCE,
            include_image: true,
          },
          skipCache: true,
        });

        if (!cancelled) {
          setSnapshot(data);
          setModelStatus(data.model_status);
          setRuntimeCapabilities(data.runtime_capabilities);
          setError(data.error || null);
          setHardwareOutputsEnabled(Boolean(data.hardware?.enabled));
          setRunning(Boolean(data.active));
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message);
        }
      }
    }

    void reconfigureRuntime();
    return () => {
      cancelled = true;
    };
  }, [hardwareOutputsEnabled, running]);

  const handleRunningChange = React.useCallback(async (nextRunning: boolean) => {
    if (!nextRunning) {
      try {
        const data = await rpcCall<LiveSnapshot>({
          func: 'stop_runtime',
          args: {
            clear_outputs: true,
          },
          skipCache: true,
        });
        setSnapshot(data);
        setModelStatus(data.model_status);
        setRuntimeCapabilities(data.runtime_capabilities);
        setRunning(false);
        setError(data.error || null);
        setHardwareOutputsEnabled(Boolean(data.hardware?.enabled));
      } catch (err: any) {
        setError(err.message);
      }
      return;
    }

    if (runtimeCapabilities && !runtimeCapabilities.live_monitor_supported) {
      setError(runtimeCapabilities.live_monitor_reason);
      return;
    }

    try {
      const data = await rpcCall<LiveSnapshot>({
        func: 'start_runtime',
        args: {
          stable_hold_seconds: HOLD_SECONDS,
          camera_width: 1280,
          camera_height: 720,
          drive_outputs: hardwareOutputsEnabled,
          standby_reminder_seconds: 20,
          category_hold_seconds: 2.0,
          min_confidence: MIN_CONFIDENCE,
          include_image: true,
        },
        skipCache: true,
      });
      setSnapshot(data);
      setModelStatus(data.model_status);
      setRuntimeCapabilities(data.runtime_capabilities);
      setError(data.error || null);
      setHardwareOutputsEnabled(Boolean(data.hardware?.enabled));
      setRunning(Boolean(data.active));
    } catch (err: any) {
      setError(err.message);
    }
  }, [hardwareOutputsEnabled, runtimeCapabilities]);

  const gateActive = snapshot ? ['tracking', 'classifying'].includes(snapshot.status) : false;
  const stableProgress = snapshot && gateActive
    ? Math.min((snapshot.tracking.stable_for_seconds / snapshot.tracking.required_hold_seconds) * 100, 100)
    : 0;

  const liveMonitorSupported = runtimeCapabilities?.live_monitor_supported ?? true;
  const hardwareOutputsAvailable = runtimeCapabilities?.hardware_outputs_available ?? false;
  const currentState = snapshot?.status || 'standby';
  const showClassBadge = Boolean(snapshot?.prediction) && (
    currentState === 'classified' || snapshot?.decision === 'low_confidence'
  );

  return (
    <>
      <Dialog open={popupOpen} onOpenChange={setPopupOpen}>
        <DialogContent className="max-w-md border-primary/10 bg-card/95 backdrop-blur-xl">
          <DialogHeader>
            <DialogTitle className="font-heading flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-primary" />
              Live Classification Locked
            </DialogTitle>
            <DialogDescription>
              The object stayed on the plate long enough to classify.
            </DialogDescription>
          </DialogHeader>
          {popupPrediction ? (
            <div className="space-y-4 py-2">
              <div className="rounded-2xl border border-primary/10 bg-primary/5 p-5 text-center">
                <div className="text-sm uppercase tracking-[0.2em] text-muted-foreground">Detected Class</div>
                <div className="mt-2 font-heading text-3xl font-bold text-primary">
                  {getCategoryLabel(popupPrediction.category)}
                </div>
                <div className="mt-2 text-sm text-muted-foreground">
                  Confidence {(popupPrediction.confidence * 100).toFixed(1)}%
                </div>
              </div>
              <div className="rounded-xl border border-white/5 bg-muted/30 p-4 text-sm text-muted-foreground">
                Model: <span className="text-foreground">{popupPrediction.model_source}</span>
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button onClick={() => setPopupOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="space-y-6">
        <div className="grid grid-cols-1 xl:grid-cols-[1.5fr,1fr] gap-6">
          <Card className="overflow-hidden border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
            <CardHeader className="border-b border-white/5">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <CardTitle className="font-heading flex items-center gap-2">
                    <Camera className="h-5 w-5 text-primary" />
                    Live Monitor
                  </CardTitle>
                  <CardDescription>
                    Shared Pi runtime with blank-reference tracking and a 2-second classification gate.
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant={running ? 'destructive' : 'default'}
                    disabled={!running && !liveMonitorSupported}
                    onClick={() => void handleRunningChange(!running)}
                  >
                    {running ? (
                      <>
                        <Square className="mr-2 h-4 w-4" />
                        Stop
                      </>
                    ) : (
                      <>
                        <Play className="mr-2 h-4 w-4" />
                        Start
                      </>
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={async () => {
                      try {
                        const data = await rpcCall<LiveSnapshot>({
                          func: 'get_runtime_snapshot',
                          args: { include_image: Boolean(running) },
                          skipCache: true,
                        });
                        setError(null);
                        setSnapshot(data);
                        setModelStatus(data.model_status);
                        setRuntimeCapabilities(data.runtime_capabilities);
                        setRunning(Boolean(data.active));
                        if (data.active) {
                          setHardwareOutputsEnabled(Boolean(data.hardware?.enabled));
                        } else if (!data.runtime_capabilities.hardware_outputs_available) {
                          setHardwareOutputsEnabled(false);
                        }
                      } catch (err: any) {
                        setError(err.message);
                      }
                    }}
                  >
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Model Status
                  </Button>
                </div>
              </div>
              <div className="flex items-center justify-between rounded-xl border border-white/5 bg-muted/20 p-3">
                <div>
                  <div className="text-sm font-medium text-foreground">Mirror Pi LEDs + buzzer</div>
                  <div className="text-xs text-muted-foreground">
                    Uses the same shared Pi runtime to drive LEDs and buzzer during the app demo.
                  </div>
                </div>
                <Switch
                  checked={hardwareOutputsEnabled}
                  disabled={!hardwareOutputsAvailable}
                  onCheckedChange={setHardwareOutputsEnabled}
                />
              </div>
            </CardHeader>
            <CardContent className="p-6 space-y-5">
              <div className="relative aspect-video overflow-hidden rounded-2xl border border-white/10 bg-muted/40">
                {snapshot?.image_b64 ? (
                  <>
                    <img
                      src={snapshot.image_b64}
                      alt="Live monitor frame"
                      className="absolute inset-0 h-full w-full object-cover"
                    />
                    {snapshot.presence?.bbox ? (
                      <div
                        className="absolute border-[3px] border-primary shadow-[0_0_0_9999px_rgba(15,23,42,0.12)]"
                        style={{
                          left: `${snapshot.presence.bbox.left_pct}%`,
                          top: `${snapshot.presence.bbox.top_pct}%`,
                          width: `${snapshot.presence.bbox.width_pct}%`,
                          height: `${snapshot.presence.bbox.height_pct}%`,
                        }}
                      />
                    ) : null}
                    <div className="absolute left-4 top-4 flex items-center gap-2">
                      <Badge variant="outline" className={cn('backdrop-blur-md', getStatusBadgeClass(snapshot.status))}>
                        {snapshot.status.replace('_', ' ').toUpperCase()}
                      </Badge>
                      {showClassBadge && snapshot?.prediction ? (
                        <Badge
                          className={
                            snapshot.decision === 'low_confidence'
                              ? 'bg-amber-500/90 text-black'
                              : 'bg-primary text-primary-foreground'
                          }
                        >
                          {snapshot.decision === 'low_confidence'
                            ? `Low Conf: ${getCategoryLabel(snapshot.prediction.category)}`
                            : getCategoryLabel(snapshot.prediction.category)}
                        </Badge>
                      ) : null}
                    </div>
                  </>
                ) : (
                  <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
                    <Camera className="h-10 w-10 mb-3" />
                    <p className="text-lg font-medium">
                      {liveMonitorSupported ? 'Live monitor is idle' : 'Live monitor is Pi-only'}
                    </p>
                    <p className="text-sm max-w-sm">
                      {liveMonitorSupported
                        ? 'Start the runtime to capture live frames from the Pi camera and draw the tracked object box.'
                        : runtimeCapabilities?.live_monitor_reason || 'This backend does not have Pi camera capture.'}
                    </p>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  <span>Stability Hold</span>
                  <span>
                    {snapshot && gateActive ? snapshot.tracking.stable_for_seconds.toFixed(1) : '0.0'}s / {HOLD_SECONDS.toFixed(1)}s
                  </span>
                </div>
                <Progress value={stableProgress} className="h-2" />
              </div>

              <div className="rounded-xl border border-white/5 bg-muted/30 p-4 text-sm">
                <div className="font-medium text-foreground">Live Status</div>
                <div className="mt-1 text-muted-foreground">
                  {snapshot?.status_message || runtimeCapabilities?.live_monitor_reason || 'No live snapshot captured yet.'}
                </div>
                {snapshot ? (
                  <div className="mt-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                    Runtime state: <span className="text-foreground">{snapshot.status.replace('_', ' ')}</span>
                  </div>
                ) : null}
                {snapshot?.image_path ? (
                  <div className="mt-2 text-xs text-muted-foreground">
                    Latest frame: <span className="text-foreground">{snapshot.image_path}</span>
                  </div>
                ) : null}
                {snapshot?.saved_capture_path ? (
                  <div className="mt-2 text-xs text-muted-foreground">
                    Archived classified frame: <span className="text-foreground">{snapshot.saved_capture_path}</span>
                  </div>
                ) : null}
              </div>

              {error ? (
                <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-500 flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
              <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                  <Camera className="h-5 w-5 text-primary" />
                  Backend Mode
                </CardTitle>
                <CardDescription>Separates general website features from Pi-only camera and GPIO features.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Badge variant="outline" className={cn(getStatusBadgeClass(liveMonitorSupported ? 'tracking' : 'standby'))}>
                  {liveMonitorSupported ? 'PI CAMERA MODE AVAILABLE' : 'UPLOAD / WEBSITE MODE ONLY'}
                </Badge>
                <div className="rounded-xl border border-white/5 bg-muted/30 p-4 text-sm text-muted-foreground space-y-2">
                  <div>
                    Host: <span className="text-foreground">{runtimeCapabilities?.host.pi_model || runtimeCapabilities?.host.platform || 'unknown'}</span>
                  </div>
                  <div>
                    Live Monitor: <span className="text-foreground">{runtimeCapabilities?.live_monitor_supported ? 'available' : 'unavailable'}</span>
                  </div>
                  <div>
                    GPIO outputs: <span className="text-foreground">{runtimeCapabilities?.hardware_outputs_available ? 'available' : 'unavailable'}</span>
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-muted/30 p-4 text-sm text-muted-foreground">
                  {runtimeCapabilities?.live_monitor_reason || 'Checking backend capabilities...'}
                </div>
              </CardContent>
            </Card>

            <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
              <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                  <Cpu className="h-5 w-5 text-primary" />
                  Model Status
                </CardTitle>
                <CardDescription>Confirms whether the real checkpoint is loaded or the app is in demo mode.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Badge variant="outline" className={cn(getStatusBadgeClass(modelStatus?.ready ? 'classified' : 'degraded'))}>
                  {modelStatus?.ready ? 'REAL CHECKPOINT READY' : modelStatus?.using_mock ? 'DEMO MODE' : 'MODEL ERROR'}
                </Badge>
                <div className="text-sm text-muted-foreground">
                  {modelStatus?.message || 'Checking model status...'}
                </div>
                <div className="rounded-xl border border-white/5 bg-muted/30 p-4 text-sm space-y-2">
                  <div>
                    <span className="text-muted-foreground">Checkpoint:</span>{' '}
                    <span className="text-foreground">{modelStatus?.checkpoint_path || 'not found'}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Model:</span>{' '}
                    <span className="text-foreground">{modelStatus?.model_name || 'n/a'}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">SHA:</span>{' '}
                    <span className="text-foreground">
                      {modelStatus?.checkpoint_sha256 ? modelStatus.checkpoint_sha256.slice(0, 12) : 'n/a'}
                    </span>
                  </div>
                </div>
                {modelStatus?.error ? (
                  <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-500">
                    {modelStatus.error}
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
              <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                  <ScanSearch className="h-5 w-5 text-primary" />
                  Tracking
                </CardTitle>
                <CardDescription>Foreground tracking comes from the blank-reference image, not a trained detector.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="rounded-xl border border-white/5 bg-muted/30 p-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Mean Diff</div>
                    <div className="mt-2 font-heading text-2xl text-foreground">
                      {snapshot?.presence?.mean_diff?.toFixed(2) || '0.00'}
                    </div>
                  </div>
                  <div className="rounded-xl border border-white/5 bg-muted/30 p-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Changed Ratio</div>
                    <div className="mt-2 font-heading text-2xl text-foreground">
                      {snapshot?.presence?.changed_ratio?.toFixed(4) || '0.0000'}
                    </div>
                  </div>
                </div>
                <div className="rounded-xl border border-white/5 bg-muted/30 p-4 text-sm text-muted-foreground space-y-2">
                  <div className="flex items-center gap-2">
                    <Clock3 className="h-4 w-4 text-primary" />
                    Stable for {snapshot && gateActive ? snapshot.tracking.stable_for_seconds.toFixed(1) : '0.0'} seconds
                  </div>
                  <div className="flex items-center gap-2">
                    {snapshot?.presence?.reference_scene_error ? (
                      <AlertTriangle className="h-4 w-4 text-rose-500" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                    )}
                    {snapshot?.presence?.reference_scene_error
                      ? 'Reference scene changed too much from calibration.'
                      : 'Reference scene still matches the calibrated plate view.'}
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
              <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                  <Cpu className="h-5 w-5 text-primary" />
                  Hardware Mirror
                </CardTitle>
                <CardDescription>Optional Pi-only output mode for LEDs and buzzer during the app demo.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Badge variant="outline" className={cn(getStatusBadgeClass(snapshot?.hardware?.enabled ? 'tracking' : 'standby'))}>
                  {snapshot?.hardware?.enabled ? 'OUTPUTS ENABLED' : hardwareOutputsAvailable ? 'OUTPUTS DISABLED' : 'PI OUTPUTS UNAVAILABLE'}
                </Badge>
                <div className="rounded-xl border border-white/5 bg-muted/30 p-4 text-sm text-muted-foreground space-y-2">
                  <div>
                    Action: <span className="text-foreground">{snapshot?.hardware?.action || 'idle'}</span>
                  </div>
                  <div>
                    Buzzer: <span className="text-foreground">{snapshot?.hardware?.buzzer_mode || 'passive'}</span>
                  </div>
                </div>
                {!hardwareOutputsAvailable ? (
                  <div className="rounded-xl border border-white/5 bg-muted/30 p-4 text-sm text-muted-foreground">
                    {runtimeCapabilities?.hardware_outputs_reason || 'GPIO outputs are not available on this backend.'}
                  </div>
                ) : null}
                {snapshot?.hardware?.error ? (
                  <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-500">
                    {snapshot.hardware.error}
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
              <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-primary" />
                  Current Prediction
                </CardTitle>
                <CardDescription>Once the object stays stable for 2 seconds, the classifier runs once for that object.</CardDescription>
              </CardHeader>
              <CardContent>
                {snapshot?.prediction && (currentState !== 'standby' || snapshot.decision === 'low_confidence') ? (
                  <div className="space-y-4">
                    <div className="rounded-2xl border border-primary/10 bg-primary/5 p-5 text-center">
                      <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                        {snapshot.decision === 'low_confidence' ? 'Low-Confidence Attempt' : 'Category'}
                      </div>
                      <div className="mt-2 font-heading text-3xl font-bold text-primary">
                        {getCategoryLabel(snapshot.prediction.category)}
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground">
                        Confidence {(snapshot.prediction.confidence * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/5 bg-muted/30 p-4 text-sm text-muted-foreground space-y-2">
                      <div>Inference: <span className="text-foreground">{snapshot.prediction.inference_time_ms.toFixed(0)} ms</span></div>
                      <div>Model source: <span className="text-foreground">{snapshot.prediction.model_source}</span></div>
                    </div>
                    {snapshot.decision === 'low_confidence' ? (
                      <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-500">
                        Confidence stayed below the active threshold, so the runtime returned to standby and did not fire the locked-class popup.
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="rounded-xl border border-white/5 bg-muted/30 p-6 text-center text-sm text-muted-foreground">
                    {currentState === 'standby'
                      ? 'Runtime is in standby. Place one item on the plate to start the 2-second gate.'
                      : 'No classification has been locked yet. Hold one item on the plate until the stability bar fills.'}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
};
