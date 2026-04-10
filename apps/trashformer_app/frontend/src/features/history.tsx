import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../components/ui/table';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { rpcCall, invalidateCache } from '../api';
import { History as HistoryIcon, Trash2, Download, Search, RefreshCw, FileText } from 'lucide-react';
import { Input } from '../components/ui/input';

interface HistoryItem {
  id: number;
  filename: string;
  category: string;
  confidence: number;
  inference_time_ms: number;
  created_at: string;
}

export const History = () => {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const data = await rpcCall({ func: 'get_history', args: { limit: 50 } });
      setHistory(data);
    } catch (err) {
      console.error('Failed to load history', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleClear = async () => {
    if (!confirm('Are you sure you want to clear all history?')) return;
    try {
      await rpcCall({ func: 'clear_history' });
      setHistory([]);
      invalidateCache(['get_history', 'get_stats']);
    } catch (err) {
      console.error('Failed to clear history', err);
    }
  };

  const filteredHistory = history.filter(item => 
    item.category.toLowerCase().includes(search.toLowerCase()) ||
    item.filename.toLowerCase().includes(search.toLowerCase())
  );

  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'plastic': return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
      case 'paper_cardboard': return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
      case 'metal_glass': return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
      case 'trash_other': return 'bg-rose-500/10 text-rose-500 border-rose-500/20';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  const getCategoryLabel = (category: string) => {
    return category.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  };

  return (
    <div className="space-y-6">
      <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
        <CardHeader className="border-b border-white/5 pb-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <CardTitle className="font-heading flex items-center gap-2 text-2xl">
                <HistoryIcon className="h-6 w-6 text-primary" />
                Classification Log
              </CardTitle>
              <CardDescription>A complete history of analyzed items and model performance metrics</CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={loadHistory} disabled={loading}>
                <RefreshCw className={loading ? "animate-spin mr-2 h-4 w-4" : "mr-2 h-4 w-4"} />
                Refresh
              </Button>
              <Button variant="destructive" size="sm" onClick={handleClear} disabled={loading || history.length === 0}>
                <Trash2 className="mr-2 h-4 w-4" />
                Clear All
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 mb-6">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input 
                placeholder="Search by category or filename..." 
                className="pl-9 bg-muted/30 border-white/5 focus-visible:ring-primary/20"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          <div className="rounded-xl border border-white/5 overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/30">
                <TableRow>
                  <TableHead className="font-heading">Timestamp</TableHead>
                  <TableHead className="font-heading">Filename</TableHead>
                  <TableHead className="font-heading">Category</TableHead>
                  <TableHead className="font-heading">Confidence</TableHead>
                  <TableHead className="font-heading text-right">Inference (ms)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredHistory.length > 0 ? (
                  filteredHistory.map((item) => (
                    <TableRow key={item.id} className="hover:bg-muted/20 border-white/5 transition-colors">
                      <TableCell className="text-muted-foreground whitespace-nowrap">
                        {new Date(item.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell className="font-medium max-w-[200px] truncate">{item.filename}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={getCategoryColor(item.category)}>
                          {getCategoryLabel(item.category)}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-sm">
                        {(item.confidence * 100).toFixed(1)}%
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm text-primary">
                        {item.inference_time_ms.toFixed(1)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={5} className="h-64 text-center">
                      <div className="flex flex-col items-center justify-center text-muted-foreground opacity-50 space-y-3">
                        <FileText className="h-12 w-12" />
                        <p className="text-lg font-medium">No records found</p>
                        <p className="text-sm max-w-xs mx-auto">Upload and classify waste items to populate the historical classification log.</p>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
