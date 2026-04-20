import React, { useState, useRef, useCallback } from 'react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Progress } from '../components/ui/progress';
import { Badge } from '../components/ui/badge';
import { cn } from '../lib/utils';
import { streamCall, invalidateCache } from '../api';
import { Upload, Camera, Zap, CheckCircle2, AlertCircle, RefreshCw, Layers } from 'lucide-react';

interface PredictionResult {
  category: string;
  confidence: number;
  inference_time_ms: number;
  model_source: string;
  checkpoint_sha256: string;
  model_name: string;
}

export const Classifier = () => {
  const [image, setImage] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>('');
  const [isClassifying, setIsClassifying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processFile(file);
    }
  };

  const processFile = (file: File) => {
    setFileName(file.name);
    setResult(null);
    setError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      setImage(e.target?.result as string);
    };
    reader.readAsDataURL(file);
  };

  const startClassification = async () => {
    if (!image) return;

    console.log('[ACTION_START] Starting classification');
    setIsClassifying(true);
    setProgress(0);
    setStatusMessage('Initializing...');
    setResult(null);
    setError(null);

    try {
      await streamCall({
        func: 'classify_image_streaming',
        args: { image_b64: image, filename: fileName },
        onChunk: (chunk) => {
          console.log('[STREAM_CHUNK]', chunk);
          if (chunk.status === 'processing') {
            setProgress(chunk.progress || 0);
            setStatusMessage(chunk.message || 'Processing...');
          } else if (chunk.status === 'success') {
            setResult(chunk.result);
            setProgress(100);
            setStatusMessage('Classification complete');
            invalidateCache(['get_history', 'get_stats']);
            console.log('[STREAM_DONE] Success');
          } else if (chunk.status === 'error') {
            setError(chunk.error);
            console.error('[STREAM_ERROR]', chunk.error);
          }
        },
        onError: (err) => {
          setError(err.message);
          console.error('[STREAM_ERROR]', err);
        }
      });
    } catch (err: any) {
      setError(err.message);
      console.error('[FETCH_ERROR]', err);
    } finally {
      setIsClassifying(false);
    }
  };

  const getCategoryPhoto = (category: string) => {
    switch (category) {
      case 'plastic': return './assets/card-plastic-bottle.jpg';
      case 'paper_cardboard': return './assets/card-cardboard-box.jpg';
      case 'metal_glass': return './assets/card-glass-bottle.jpg';
      case 'trash_other': return './assets/card-organic-waste.jpg';
      default: return null;
    }
  };

  const getCategoryLabel = (category: string) => {
    return category.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upload Section */}
        <Card className="overflow-hidden border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
          <CardHeader>
            <CardTitle className="font-heading flex items-center gap-2">
              <Camera className="h-5 w-5 text-primary" />
              Image Input
            </CardTitle>
            <CardDescription>Upload a photo of waste for real-time classification</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div 
              className={cn(
                "relative aspect-video rounded-xl border-2 border-dashed border-muted-foreground/20 bg-muted/30 flex flex-col items-center justify-center transition-all overflow-hidden",
                !image && "hover:border-primary/50 hover:bg-primary/5 cursor-pointer"
              )}
              onClick={() => !isClassifying && fileInputRef.current?.click()}
            >
              {image ? (
                <>
                  <img src={image} alt="Upload preview" className="absolute inset-0 w-full h-full object-contain" />
                  <div className="absolute inset-0 bg-black/40 opacity-0 hover:opacity-100 flex items-center justify-center transition-opacity">
                    <Button variant="secondary" size="sm">Change Image</Button>
                  </div>
                </>
              ) : (
                <div className="text-center p-6">
                  <Upload className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                  <p className="text-sm font-medium">Click to upload or drag and drop</p>
                  <p className="text-xs text-muted-foreground mt-1">PNG, JPG, or WEBP up to 5MB</p>
                </div>
              )}
            </div>
            <input 
              type="file" 
              ref={fileInputRef} 
              className="hidden" 
              accept="image/*" 
              onChange={handleFileChange} 
            />
            
            <Button 
              className="w-full h-12 text-lg font-heading shadow-lg shadow-primary/20" 
              disabled={!image || isClassifying}
              onClick={startClassification}
            >
              {isClassifying ? (
                <>
                  <RefreshCw className="mr-2 h-5 w-5 animate-spin" />
                  Classifying...
                </>
              ) : (
                <>
                  <Zap className="mr-2 h-5 w-5" />
                  Classify Waste
                </>
              )}
            </Button>

            {isClassifying && (
              <div className="space-y-2 animate-in fade-in slide-in-from-top-2 duration-300">
                <div className="flex justify-between text-xs font-medium">
                  <span className="text-primary">{statusMessage}</span>
                  <span>{progress}%</span>
                </div>
                <Progress value={progress} className="h-2" />
              </div>
            )}

            {error && (
              <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Results Section */}
        <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl flex flex-col">
          <CardHeader>
            <CardTitle className="font-heading flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-primary" />
              Analysis Result
            </CardTitle>
            <CardDescription>AI-powered waste classification output</CardDescription>
          </CardHeader>
          <CardContent className="flex-1 flex flex-col justify-center">
            {result ? (
              <div className="space-y-6 animate-in zoom-in-95 duration-500">
                <div className="relative group">
                  <div className="absolute -inset-1 bg-gradient-to-r from-primary/50 to-emerald-400/50 rounded-xl blur opacity-25 group-hover:opacity-50 transition duration-1000 group-hover:duration-200"></div>
                  <div className="relative aspect-video rounded-xl overflow-hidden bg-muted border border-white/10">
                    <img 
                      src={getCategoryPhoto(result.category) || ''} 
                      alt={result.category} 
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-black/80 to-transparent">
                      <Badge className="bg-primary hover:bg-primary/90 text-primary-foreground text-sm py-1 px-3">
                        {getCategoryLabel(result.category)}
                      </Badge>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl bg-primary/5 border border-primary/10 flex flex-col items-center justify-center text-center">
                    <div className="text-3xl font-bold font-heading text-primary">
                      {(result.confidence * 100).toFixed(1)}%
                    </div>
                    <div className="text-xs text-muted-foreground mt-1 uppercase tracking-wider font-semibold">Confidence</div>
                  </div>
                  <div className="p-4 rounded-xl bg-primary/5 border border-primary/10 flex flex-col items-center justify-center text-center">
                    <div className="text-3xl font-bold font-heading text-primary">
                      {result.inference_time_ms.toFixed(0)}<span className="text-sm font-normal ml-0.5">ms</span>
                    </div>
                    <div className="text-xs text-muted-foreground mt-1 uppercase tracking-wider font-semibold">Inference</div>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-muted/50 border border-white/5 space-y-3">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <Layers className="h-4 w-4 text-primary" />
                    Classification Details
                  </div>
                  <div className="text-sm text-muted-foreground leading-relaxed">
                    The TrashformerPro model identified this item as <span className="text-foreground font-semibold">{getCategoryLabel(result.category)}</span>. 
                    This classification was performed using a MobileNetV3-based architecture optimized for edge devices.
                  </div>
                  <div className="rounded-lg border border-white/5 bg-background/40 p-3 text-xs text-muted-foreground space-y-1">
                    <div>Model source: <span className="text-foreground">{result.model_source}</span></div>
                    <div>Model name: <span className="text-foreground">{result.model_name}</span></div>
                    <div>
                      SHA: <span className="text-foreground">{result.checkpoint_sha256 ? result.checkpoint_sha256.slice(0, 12) : 'demo'}</span>
                    </div>
                  </div>
                  {result.model_source === 'mock' ? (
                    <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-500 text-sm flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 shrink-0" />
                      This result came from demo mode, not a real checkpoint.
                    </div>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="h-full min-h-[300px] flex flex-col items-center justify-center text-center p-6 space-y-4 opacity-50">
                <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center">
                  <Zap className="h-8 w-8 text-muted-foreground" />
                </div>
                <div className="space-y-1">
                  <p className="text-lg font-medium">Awaiting Data</p>
                  <p className="text-sm text-muted-foreground max-w-[240px]">Upload and classify an image to see prediction results and model performance.</p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
