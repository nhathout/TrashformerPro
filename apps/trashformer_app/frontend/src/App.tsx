import React, { useState, useEffect } from 'react';
import { cn } from './lib/utils';
import { Button } from './components/ui/button';
import { Separator } from './components/ui/separator';
import { Badge } from './components/ui/badge';
import { 
  LayoutDashboard, 
  History as HistoryIcon, 
  BarChart3, 
  Zap, 
  Menu, 
  Leaf, 
  Cpu, 
  Database, 
  ShieldCheck,
  ChevronRight,
  Globe
} from 'lucide-react';
import { SiPytorch, SiPython, SiNvidia, SiRaspberrypi } from 'react-icons/si';
import { Classifier } from './features/classifier';
import { LiveMonitor } from './features/live-monitor';
import { History } from './features/history';
import { Insights } from './features/insights';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState('classifier');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    console.log("RENDER_SUCCESS");
  }, []);

  const navItems = [
    { id: 'classifier', label: 'AI Classifier', icon: Zap },
    { id: 'live-monitor', label: 'Live Monitor', icon: Cpu },
    { id: 'history', label: 'Classification Log', icon: HistoryIcon },
    { id: 'insights', label: 'Data Insights', icon: BarChart3 },
  ];

  const renderContent = () => {
    switch (activeTab) {
      case 'classifier': return <Classifier />;
      case 'live-monitor': return <LiveMonitor />;
      case 'history': return <History />;
      case 'insights': return <Insights />;
      default: return <Classifier />;
    }
  };

  return (
    <div className="flex h-screen flex-col md:flex-row bg-background text-foreground overflow-hidden">
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex w-72 flex-col border-r bg-card/30 backdrop-blur-xl">
        <div className="p-6 flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-primary flex items-center justify-center shadow-lg shadow-primary/20">
            <Leaf className="h-6 w-6 text-primary-foreground" />
          </div>
          <div>
            <h1 className="font-heading font-bold text-lg tracking-tight">TrashformerPro</h1>
            <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-[0.2em]">Sustainability Engine</p>
          </div>
        </div>
        
        <nav className="flex-1 px-4 py-2 space-y-2">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all group",
                activeTab === item.id 
                  ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20" 
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <item.icon className={cn("h-5 w-5", activeTab === item.id ? "text-primary-foreground" : "text-primary/70")} />
              {item.label}
              {activeTab === item.id && <ChevronRight className="ml-auto h-4 w-4 opacity-50" />}
            </button>
          ))}
        </nav>

        <div className="p-6 mt-auto border-t border-white/5 space-y-6">
          <div className="p-4 rounded-xl bg-primary/5 border border-primary/10">
            <div className="flex items-center gap-2 text-xs font-semibold text-primary uppercase tracking-wider mb-2">
              <Cpu className="h-3 w-3" />
              System Status
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Model Check</span>
              <span className="flex items-center gap-1.5 text-primary">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                Live Monitor
              </span>
            </div>
          </div>

          <div className="space-y-3">
            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest text-center">Powered By</p>
            <div className="grid grid-cols-2 gap-3 opacity-60">
              <div className="flex items-center justify-center p-2 rounded-lg bg-muted/50 border border-white/5"><SiPytorch className="h-5 w-5" /></div>
              <div className="flex items-center justify-center p-2 rounded-lg bg-muted/50 border border-white/5"><SiNvidia className="h-5 w-5" /></div>
              <div className="flex items-center justify-center p-2 rounded-lg bg-muted/50 border border-white/5"><SiPython className="h-5 w-5" /></div>
              <div className="flex items-center justify-center p-2 rounded-lg bg-muted/50 border border-white/5"><SiRaspberrypi className="h-5 w-5" /></div>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile Nav */}
      <header className="md:hidden flex items-center justify-between px-6 py-4 border-b bg-background/80 backdrop-blur-md sticky top-0 z-50">
        <div className="flex items-center gap-2">
          <Leaf className="h-6 w-6 text-primary" />
          <span className="font-heading font-bold text-lg">TrashformerPro</span>
        </div>
        <Button variant="ghost" size="icon" onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>
          <Menu className="h-6 w-6" />
        </Button>
      </header>

      {mobileMenuOpen && (
        <div className="md:hidden fixed inset-0 z-40 bg-background/95 backdrop-blur-md pt-20 px-6 animate-in fade-in slide-in-from-top-4 duration-300">
          <div className="space-y-3">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => { setActiveTab(item.id); setMobileMenuOpen(false); }}
                className={cn(
                  "w-full flex items-center gap-4 px-6 py-4 rounded-2xl text-lg font-medium transition-all",
                  activeTab === item.id 
                    ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20" 
                    : "text-muted-foreground bg-muted/50"
                )}
              >
                <item.icon className="h-6 w-6" />
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto bg-mesh relative">
        <div className="absolute top-0 left-0 right-0 h-[400px] bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />
        
        <div className="max-w-7xl mx-auto px-6 py-8 md:py-12 space-y-12 relative z-10">
          {/* Hero Section - Only shown on Classifier tab */}
          {activeTab === 'classifier' && (
            <section className="animate-in fade-in slide-in-from-bottom-4 duration-700">
              <div className="relative rounded-3xl overflow-hidden h-[300px] md:h-[400px] shadow-2xl group border border-white/10">
                <img 
                  src="./assets/hero-sorting-facility.jpg" 
                  alt="Waste Sorting Facility" 
                  className="absolute inset-0 w-full h-full object-cover transition-transform duration-10000 group-hover:scale-110"
                />
                <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/40 to-transparent flex flex-col justify-center p-8 md:p-12">
                  <Badge className="w-fit mb-4 bg-primary/20 hover:bg-primary/30 text-primary border-primary/30 backdrop-blur-md">
                    Enterprise Grade AI
                  </Badge>
                  <h2 className="font-heading text-4xl md:text-6xl font-bold text-white max-w-2xl leading-tight tracking-tight">
                    Smart Waste <span className="text-primary">Classification</span>
                  </h2>
                  <p className="text-white/70 text-lg md:text-xl max-w-lg mt-4 leading-relaxed font-medium">
                    Automate recycling sorting with MobileNetV3 accuracy. Real-time vision intelligence for a sustainable future.
                  </p>
                  <div className="flex flex-wrap gap-4 mt-8">
                    <Button size="lg" className="rounded-full px-8 shadow-xl shadow-primary/30" onClick={() => setActiveTab('classifier')}>
                      Start Scanning
                    </Button>
                    <Button variant="outline" size="lg" className="rounded-full px-8 bg-white/5 backdrop-blur-md border-white/10 hover:bg-white/10" onClick={() => setActiveTab('insights')}>
                      View Insights
                    </Button>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
                <div className="p-6 rounded-2xl bg-card/40 backdrop-blur-sm border border-white/5 space-y-3 flex flex-col items-center text-center">
                  <div className="h-12 w-12 rounded-full bg-blue-500/10 flex items-center justify-center">
                    <ShieldCheck className="h-6 w-6 text-blue-500" />
                  </div>
                  <h3 className="font-heading font-bold text-lg">98% Accuracy</h3>
                  <p className="text-sm text-muted-foreground">Advanced convolutional neural networks trained on 100k+ waste samples.</p>
                </div>
                <div className="p-6 rounded-2xl bg-card/40 backdrop-blur-sm border border-white/5 space-y-3 flex flex-col items-center text-center">
                  <div className="h-12 w-12 rounded-full bg-amber-500/10 flex items-center justify-center">
                    <Zap className="h-6 w-6 text-amber-500" />
                  </div>
                  <h3 className="font-heading font-bold text-lg">Real-Time Speed</h3>
                  <p className="text-sm text-muted-foreground">Inference times under 100ms optimized for Raspberry Pi and edge hardware.</p>
                </div>
                <div className="p-6 rounded-2xl bg-card/40 backdrop-blur-sm border border-white/5 space-y-3 flex flex-col items-center text-center">
                  <div className="h-12 w-12 rounded-full bg-emerald-500/10 flex items-center justify-center">
                    <Globe className="h-6 w-6 text-emerald-500" />
                  </div>
                  <h3 className="font-heading font-bold text-lg">Eco-Friendly</h3>
                  <p className="text-sm text-muted-foreground">Minimizing landfill waste through precise automated material recovery.</p>
                </div>
              </div>
            </section>
          )}

          {/* Active Feature Content */}
          <section className="animate-in fade-in slide-in-from-bottom-4 duration-1000 delay-200">
            {renderContent()}
          </section>
        </div>

        {/* Technical Footer */}
        <footer className="max-w-7xl mx-auto px-6 py-12 border-t border-white/5">
          <div className="flex flex-col md:flex-row justify-between items-center gap-8">
            <div className="flex items-center gap-3 grayscale opacity-40 hover:grayscale-0 hover:opacity-100 transition-all duration-500">
              <Leaf className="h-5 w-5 text-primary" />
              <span className="font-heading font-bold text-muted-foreground">TrashformerPro <span className="text-[10px] ml-1">v2.4.0</span></span>
            </div>
            
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2 text-muted-foreground/60 text-xs font-medium uppercase tracking-[0.2em]">
                <Database className="h-4 w-4" />
                SQLite Core
              </div>
              <div className="flex items-center gap-2 text-muted-foreground/60 text-xs font-medium uppercase tracking-[0.2em]">
                <Cpu className="h-4 w-4" />
                ARM v8 Optimized
              </div>
            </div>

            <p className="text-xs text-muted-foreground font-medium">
              &copy; 2026 Trashformer AI Systems. All rights reserved.
            </p>
          </div>
        </footer>
      </main>
    </div>
  );
};

export default App;
