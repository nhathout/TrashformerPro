import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { rpcCall } from '../api';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, AreaChart, Area } from 'recharts';
import { BarChart3, PieChart as PieChartIcon, TrendingUp, Zap, Box, Activity, Clock } from 'lucide-react';

interface Stats {
  total_count: number;
  category_counts: Record<string, number>;
  avg_inference_time: number;
}

export const Insights = () => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(false);

  const loadStats = useCallback(async () => {
    setLoading(true);
    try {
      const data = await rpcCall({ func: 'get_stats' });
      setStats(data);
    } catch (err) {
      console.error('Failed to load stats', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  if (!stats) return null;

  const COLORS = ['#3b82f6', '#f59e0b', '#10b981', '#f43f5e'];
  
  const pieData = Object.entries(stats.category_counts).map(([name, value]) => ({
    name: name.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
    value
  })).filter(d => d.value > 0);

  const barData = Object.entries(stats.category_counts).map(([name, value]) => ({
    name: name.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
    count: value
  }));

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div className="rounded-xl bg-primary/10 p-3">
                <Box className="h-6 w-6 text-primary" />
              </div>
              <Activity className="h-4 w-4 text-muted-foreground/30" />
            </div>
            <div className="mt-4">
              <div className="text-4xl font-bold font-heading">{stats.total_count}</div>
              <div className="text-sm text-muted-foreground font-medium uppercase tracking-wider mt-1">Total Classified</div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div className="rounded-xl bg-primary/10 p-3">
                <Clock className="h-6 w-6 text-primary" />
              </div>
              <Zap className="h-4 w-4 text-muted-foreground/30" />
            </div>
            <div className="mt-4">
              <div className="text-4xl font-bold font-heading">{stats.avg_inference_time.toFixed(1)}<span className="text-lg ml-1 text-muted-foreground">ms</span></div>
              <div className="text-sm text-muted-foreground font-medium uppercase tracking-wider mt-1">Avg. Inference</div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div className="rounded-xl bg-primary/10 p-3">
                <TrendingUp className="h-6 w-6 text-primary" />
              </div>
              <TrendingUp className="h-4 w-4 text-muted-foreground/30" />
            </div>
            <div className="mt-4">
              <div className="text-4xl font-bold font-heading">
                {stats.total_count > 0 ? (stats.category_counts['plastic'] / stats.total_count * 100).toFixed(0) : 0}%
              </div>
              <div className="text-sm text-muted-foreground font-medium uppercase tracking-wider mt-1">Plastic Ratio</div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Category Distribution - Pie Chart */}
        <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
          <CardHeader>
            <CardTitle className="font-heading flex items-center gap-2">
              <PieChartIcon className="h-5 w-5 text-primary" />
              Waste Distribution
            </CardTitle>
            <CardDescription>Composition of waste by category</CardDescription>
          </CardHeader>
          <CardContent className="h-[350px]">
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={80}
                    outerRadius={120}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="none"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px' }}
                    itemStyle={{ color: 'hsl(var(--foreground))' }}
                  />
                  <Legend verticalAlign="bottom" height={36}/>
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-muted-foreground opacity-50">
                No data available
              </div>
            )}
          </CardContent>
        </Card>

        {/* Inference Load - Bar Chart */}
        <Card className="border-primary/10 bg-card/50 backdrop-blur-sm shadow-xl">
          <CardHeader>
            <CardTitle className="font-heading flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-primary" />
              Classification Volume
            </CardTitle>
            <CardDescription>Total items processed per category</CardDescription>
          </CardHeader>
          <CardContent className="h-[350px]">
            {stats.total_count > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--muted-foreground))" opacity={0.1} />
                  <XAxis 
                    dataKey="name" 
                    tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }} 
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis 
                    tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip 
                    cursor={{ fill: 'hsl(var(--muted))', opacity: 0.2 }}
                    contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px' }}
                  />
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={[6, 6, 0, 0]} barSize={40} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-muted-foreground opacity-50">
                No data available
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
