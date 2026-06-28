"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  Sparkles,
  Code,
  Search,
  Check,
  X,
  ArrowRight,
  ArrowDown,
  Terminal,
  Cpu,
  Layers,
  Workflow,
  Server,
  Lock,
  Database,
  Boxes,
} from "lucide-react";

const TERMINAL_STEPS = [
  { agent: "planner" as const, text: "Parsing prompt → extracting stack, features, target files..." },
  { agent: "planner" as const, text: "Plan validated ✓ — 6 files, FastAPI + React, 4 features" },
  { agent: "architect" as const, text: "Resolving dependency order — models before routes before integration" },
  { agent: "coder" as const, text: "Writing db/models.py — injecting 3 repo context chunks from Qdrant" },
  { agent: "coder" as const, text: "db/models.py generated successfully ✓" },
  { agent: "coder" as const, text: "Writing api/routes.py — sibling context: db/models.py loaded" },
  { agent: "integrator" as const, text: "Cross-file validation — checking exports, paths, interface contracts" },
  { agent: "integrator" as const, text: "Applying structured fixes — resolving route import paths" },
  { agent: "done" as const, text: "Generation complete — 6 files, 0 import errors, streamed via WebSocket" },
];

export default function Home() {
  const [currentStep, setCurrentStep] = useState(0);
  const terminalContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (currentStep < TERMINAL_STEPS.length - 1) {
      const timer = setTimeout(() => {
        setCurrentStep((prev) => prev + 1);
      }, 450);
      return () => clearTimeout(timer);
    } else {
      const timer = setTimeout(() => {
        setCurrentStep(0);
      }, 4000);
      return () => clearTimeout(timer);
    }
  }, [currentStep]);

  useEffect(() => {
    if (terminalContainerRef.current) {
      terminalContainerRef.current.scrollTop = terminalContainerRef.current.scrollHeight;
    }
  }, [currentStep]);

  const getBadgeStyles = (agent: string) => {
    switch (agent) {
      case "planner":
        return { text: "planner", className: "bg-[rgba(167,139,250,0.1)] text-[#a78bfa] border-[rgba(167,139,250,0.2)] font-mono" };
      case "architect":
        return { text: "architect", className: "bg-[rgba(0,229,160,0.1)] text-[#00e5a0] border-[rgba(0,229,160,0.2)] font-mono" };
      case "coder":
        return { text: "coder", className: "bg-[rgba(59,130,246,0.1)] text-[#60a5fa] border-[rgba(59,130,246,0.2)] font-mono" };
      case "critic":
        return { text: "critic", className: "bg-[rgba(250,204,21,0.1)] text-[#facc15] border-[rgba(250,204,21,0.2)] font-mono" };
      case "integrator":
        return { text: "integrator", className: "bg-[rgba(239,68,68,0.1)] text-[#f87171] border-[rgba(239,68,68,0.2)] font-mono" };
      case "done":
        return { text: "done", className: "bg-[rgba(0,229,160,0.15)] text-[#00e5a0] border-[rgba(0,229,160,0.3)] font-mono font-semibold" };
      default:
        return { text: agent, className: "bg-zinc-800 text-zinc-400 border-zinc-700 font-mono" };
    }
  };

  return (
    <div
      className="min-h-screen flex flex-col relative overflow-hidden font-body selection:bg-[#a78bfa]/30 selection:text-white"
      style={{ background: "#090910", color: "#f0f0f5" }}
    >
      {/* Subtle background glow highlights */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-violet-900/10 filter blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[20%] right-[-10%] w-[60%] h-[60%] rounded-full bg-[#a78bfa]/5 filter blur-[150px] pointer-events-none" />

      {/* Navigation */}
      <nav
        className="relative z-10 flex items-center justify-between px-8 py-4 border-b border-[#1f1f2e]"
        style={{ background: "rgba(9,9,16,0.8)", backdropFilter: "blur(16px)" }}
      >
        <div className="flex items-center gap-3">
          <img src="/logo.png" alt="Adra-AI" className="w-8 h-8 rounded-lg object-contain" />
          <span className="text-lg font-bold text-white tracking-tight font-heading">Adra-AI</span>
        </div>

        {/* <div className="flex items-center gap-3">
          <Link
            href="/auth/signin"
            className="btn-secondary text-sm px-5 py-2 font-medium rounded-xl border border-[#1f1f2e] bg-[#111119] hover:bg-[#1e1e2f] text-white transition-all duration-200"
            id="sign-in-nav"
          >
            Sign In
          </Link>
        </div> */}

      </nav>

      {/* Hero Section */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-start px-6 pt-16 pb-24 text-center">
        {/* Eyebrow Tech Stack Label */}
        {/* <div
          className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-mono font-medium mb-6 transition-all duration-300"
          style={{
            background: "rgba(0, 229, 160, 0.05)",
            border: "1px solid rgba(0, 229, 160, 0.2)",
            color: "#00e5a0",
          }}
        >
          <span className="w-2 h-2 rounded-full bg-[#00e5a0] animate-pulse" />
          LangGraph · Qdrant · FastAPI · Next.js
        </div> */}

        {/* Headline */}
        <h1 className="text-4xl sm:text-5xl lg:text-7xl font-extrabold text-white tracking-tighter leading-[1.08] mb-6 max-w-4xl font-heading">
          Your codebase has context.
          <br />
          Most AI agents ignore it.
          <br />
          <span className="text-[#a78bfa] drop-shadow-[0_0_15px_rgba(167,139,250,0.15)]">Adra-AI doesn't.</span>
        </h1>

        {/* Subheadline */}
        <p className="text-base sm:text-lg max-w-3xl mx-auto mb-10 leading-relaxed text-[#6b6b80] font-body">
          Adra-AI is a multi-agent coding intelligence platform that reads, indexes, and reasons over your entire repository before writing a single line of code - so generated code actually fits what you already built.
        </p>

        {/* CTA Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16 w-full max-w-md">
          <Link
            href="/auth/signin"
            className="btn-primary text-sm w-full sm:w-auto font-semibold font-body inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl transition-all duration-200 cursor-pointer glow-btn text-white"
            id="hero-cta-start"
            style={{ background: "linear-gradient(135deg, #a78bfa 0%, #6366f1 100%)" }}
          >
            Start Building Free
            <ArrowRight className="w-4 h-4" />
          </Link>
          <a
            href="https://github.com/adityaxxz/Adra-AI"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary text-sm w-full sm:w-auto font-medium font-body flex items-center justify-center gap-2 border border-[#1f1f2e] bg-[#111119] hover:bg-[#1e1e2f] text-[#f0f0f5] px-6 py-3 rounded-xl transition-all duration-200"
            id="hero-cta-source"
          >
            <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
              <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.464-1.11-1.464-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.579.688.481C19.138 20.161 22 16.416 22 12c0-5.523-4.477-10-10-10z" />
            </svg>
            <span>View Source Code</span>
          </a>
        </div>

        {/* Metrics Strip */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl w-full mx-auto px-4 py-8 rounded-2xl border border-[#1f1f2e] bg-[#111119]/40 backdrop-blur-md mb-24">
          <div className="text-center p-4 border-r border-[#1f1f2e] max-lg:border-r-0 max-sm:border-b last:border-b-0 last:border-r-0">
            <div className="text-3xl font-extrabold text-[#00e5a0] font-mono tracking-tight">90%+</div>
            <div className="text-sm font-semibold text-[#f0f0f5] mt-1.5 font-body">Indexing Cost Reduction</div>
            <div className="text-xs text-[#6b6b80] mt-1 font-mono">from SHA256 incremental indexing</div>
          </div>
          <div className="text-center p-4 border-r border-[#1f1f2e] max-lg:border-r-0 max-sm:border-b last:border-b-0 last:border-r-0">
            <div className="text-3xl font-extrabold text-[#a78bfa] font-mono tracking-tight">7+</div>
            <div className="text-sm font-semibold text-[#f0f0f5] mt-1.5 font-body">Languages Supported</div>
            <div className="text-xs text-[#6b6b80] mt-1 font-mono">including Python, TS, JS, Go</div>
          </div>
          <div className="text-center p-4 border-r border-[#1f1f2e] max-sm:border-b last:border-b-0 last:border-r-0">
            <div className="text-3xl font-extrabold text-[#4cc2e9] font-mono tracking-tight">5</div>
            <div className="text-sm font-semibold text-[#f0f0f5] mt-1.5 font-body">Specialized Agents</div>
            <div className="text-xs text-[#6b6b80] mt-1 font-mono">in a LangGraph StateGraph</div>
          </div>
          <div className="text-center p-4">
            <div className="text-3xl font-extrabold text-[#f59e0b] font-mono tracking-tight">3</div>
            <div className="text-sm font-semibold text-[#f0f0f5] mt-1.5 font-body">Operation Modes</div>
            <div className="text-xs text-[#6b6b80] mt-1 font-mono">Build, Edit, or Q&A</div>
          </div>
        </div>

        {/* Animated Terminal Section */}
        <div className="w-full max-w-4xl mx-auto mb-32 px-4">
          <div className="relative rounded-2xl border border-[#1f1f2e] bg-[#111119] shadow-2xl overflow-hidden">
            {/* Terminal Top Bar */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#1f1f2e] bg-[#090910]">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-full bg-[#ef4444]" />
                <span className="w-3 h-3 rounded-full bg-[#facc15]" />
                <span className="w-3 h-3 rounded-full bg-[#00e5a0]" />
              </div>
              <div className="text-xs font-mono text-[#6b6b80] select-none flex items-center gap-1.5">
                <Terminal className="w-3.5 h-3.5 text-[#a78bfa]" />
                agent_execution_trace.sh
              </div>
              <div className="w-12" />
            </div>

            {/* Terminal Window Content */}
            <div
              ref={terminalContainerRef}
              className="p-6 overflow-y-auto h-[420px] bg-[#111119] scrollbar-hide select-none"
              style={{ userSelect: 'none' }}
            >
              <div className="font-mono text-left space-y-3 text-xs sm:text-sm select-none">
                {TERMINAL_STEPS.slice(0, currentStep + 1).map((step, idx) => {
                  const badge = getBadgeStyles(step.agent);
                  return (
                    <div
                      key={idx}
                      className="flex flex-col sm:flex-row sm:items-start gap-2 sm:gap-3 py-1 border-b border-[#1f1f2e]/10 last:border-b-0 animate-fade-in select-none"
                    >
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded text-[10px] uppercase font-extrabold border tracking-wider text-center w-[96px] shrink-0 ${badge.className}`}
                      >
                        {badge.text}
                      </span>
                      <span className="text-[#f0f0f5] font-light leading-relaxed select-none font-mono">
                        {step.text}
                      </span>
                    </div>
                  );
                })}
                {currentStep < TERMINAL_STEPS.length - 1 ? (
                  <div className="flex items-center gap-2 text-[#a78bfa] text-xs pt-2 animate-pulse font-mono">
                    <span className="w-1.5 h-3 bg-[#a78bfa]" />
                    <span>Agent execution in progress...</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-[#00e5a0] text-xs pt-4 font-mono select-none">
                    <Check className="w-4 h-4 animate-bounce" />
                    <span>Trace execution completed.</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Problem Section */}
        <div className="w-full max-w-5xl mx-auto mb-32 px-4 text-left">
          <div className="text-center mb-16">
            {/* <span className="text-xs font-mono font-bold tracking-widest text-[#a78bfa] uppercase px-3 py-1 rounded-full border border-[#a78bfa]/20 bg-[#a78bfa]/5">
              The Problem
            </span> */}
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white mt-4 font-heading tracking-tight">
              Generic AI codegen doesn't know what you already built.
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Card 1 - Bad */}
            <div className="card p-6 border border-[#1f1f2e] border-t-[3px] border-t-red-500/30 opacity-75 hover:opacity-100 transition-all duration-300 bg-[#111119]/50 flex flex-col justify-between">
              <div>
                <div className="flex justify-between items-start mb-4">
                  <span className="text-xs font-mono text-red-400 uppercase tracking-widest font-bold">
                    Legacy Approach
                  </span>
                  <X className="w-4 h-4 text-red-500/50" />
                </div>
                <h3 className="text-xl font-bold text-white font-heading mb-1">Generic RAG / Copilot</h3>
                <h4 className="text-sm font-semibold text-red-400 font-body mb-3">Stateless generation</h4>
                <p className="text-sm text-[#6b6b80] leading-relaxed font-body">
                  Provides code suggestions based on training data only. Has zero awareness of your existing authentication middleware, shared utility helpers, or custom folder structure and naming conventions.
                </p>
              </div>
            </div>

            {/* Card 2 - Bad */}
            <div className="card p-6 border border-[#1f1f2e] border-t-[3px] border-t-red-500/30 opacity-75 hover:opacity-100 transition-all duration-300 bg-[#111119]/50 flex flex-col justify-between">
              <div>
                <div className="flex justify-between items-start mb-4">
                  <span className="text-xs font-mono text-red-400 uppercase tracking-widest font-bold">
                    Legacy Approach
                  </span>
                  <X className="w-4 h-4 text-red-500/50" />
                </div>
                <h3 className="text-xl font-bold text-white font-heading mb-1">Single-agent chatbots</h3>
                <h4 className="text-sm font-semibold text-red-400 font-body mb-3">No architectural reasoning</h4>
                <p className="text-sm text-[#6b6b80] leading-relaxed font-body">
                  A single model attempts to plan, write, and validate code all at once. As the context window fills up, hallucinations compound and cross-file consistency breaks, producing code that won't run.
                </p>
              </div>
            </div>

            {/* Card 3 - Good */}
            <div className="card p-6 border border-[#a78bfa]/30 hover:border-[#a78bfa] shadow-[0_0_20px_rgba(167,139,250,0.05)] hover:shadow-[0_0_30px_rgba(167,139,250,0.15)] transition-all duration-300 bg-[#111119] flex flex-col justify-between relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-[#a78bfa]/5 rounded-full filter blur-xl pointer-events-none" />
              <div>
                <div className="flex justify-between items-start mb-4">
                  <span className="text-xs font-mono text-[#00e5a0] uppercase tracking-widest font-bold px-2 py-0.5 rounded border border-[#00e5a0]/30 bg-[#00e5a0]/10">
                    The Adra Way
                  </span>
                  <Check className="w-4 h-4 text-[#00e5a0]" />
                </div>
                <h3 className="text-xl font-bold text-white font-heading mb-1">Adra-AI</h3>
                <h4 className="text-sm font-semibold text-[#a78bfa] font-body mb-3">AST-guided code-aware chunking</h4>
                <p className="text-sm text-[#f0f0f5] leading-relaxed font-body">
                  Our Repository Agent scans, parses, and indexes your entire codebase into Qdrant using AST-guided, code-aware chunking. By respecting class, function, and import boundaries, we preserve the logical context of your files.
                </p>
              </div>
            </div>

            {/* Card 4 - Good */}
            <div className="card p-6 border border-[#a78bfa]/30 hover:border-[#a78bfa] shadow-[0_0_20px_rgba(167,139,250,0.05)] hover:shadow-[0_0_30px_rgba(167,139,250,0.15)] transition-all duration-300 bg-[#111119] flex flex-col justify-between relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-[#a78bfa]/5 rounded-full filter blur-xl pointer-events-none" />
              <div>
                <div className="flex justify-between items-start mb-4">
                  <span className="text-xs font-mono text-[#00e5a0] uppercase tracking-widest font-bold px-2 py-0.5 rounded border border-[#00e5a0]/30 bg-[#00e5a0]/10">
                    The Adra Way
                  </span>
                  <Check className="w-4 h-4 text-[#00e5a0]" />
                </div>
                <h3 className="text-xl font-bold text-white font-heading mb-1">Adra-AI</h3>
                <h4 className="text-sm font-semibold text-[#a78bfa] font-body mb-3">Specialized agent pipeline</h4>
                <p className="text-sm text-[#f0f0f5] leading-relaxed font-body">
                  Planning, architecture design, coding, and integration are split across distinct, specialized LangGraph agents. Each has its own state and specific scope, eliminating model overload.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Operation Modes Section */}
        <div className="w-full max-w-5xl mx-auto mb-32 px-4 text-left">
          <div className="text-center mb-16">
            {/* <span className="text-xs font-mono font-bold tracking-widest text-[#00e5a0] uppercase px-3 py-1 rounded-full border border-[#00e5a0]/20 bg-[#00e5a0]/5">
              What Adra-AI Does
            </span> */}
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white mt-4 font-heading tracking-tight">
              Three modes. One intelligent platform.
            </h2>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Card 1 - Project Generation */}
            <div className="card p-6 border border-[#1f1f2e] border-t-2 border-t-[#a78bfa]/30 hover:border-[#a78bfa] hover:shadow-[0_0_25px_rgba(167,139,250,0.1)] transition-all duration-300 bg-[#111119] flex flex-col justify-between min-h-[320px]">
              <div>
                <div className="w-10 h-10 rounded-xl bg-[#a78bfa]/10 border border-[#a78bfa]/20 flex items-center justify-center text-[#a78bfa] mb-4">
                  <Sparkles className="w-5 h-5" />
                </div>
                <h3 className="text-xl font-bold text-white font-heading mb-2">Project Generation</h3>
                <p className="text-sm text-[#6b6b80] leading-relaxed font-body mb-6">
                  Describe your app in plain English. Adra-AI plans the architecture, orders the files by dependency, writes each one with cross-file context, and validates the whole codebase before handing it to you.
                </p>
              </div>
              <div className="pt-4 border-t border-[#1f1f2e] mt-auto">
                <div className="text-[10px] uppercase font-bold tracking-wider text-[#6b6b80] font-mono mb-2">
                  Pipeline Trace
                </div>
                <div className="text-[10px] sm:text-xs font-mono text-[#a78bfa] select-none bg-[#090910] px-2.5 py-1.5 rounded border border-[#1f1f2e] inline-block">
                  Planner → Architect → Coder → Integrator
                </div>
              </div>
            </div>

            {/* Card 2 - Repository Editing */}
            <div className="card p-6 border border-[#1f1f2e] border-t-2 border-t-[#a78bfa]/30 hover:border-[#a78bfa] hover:shadow-[0_0_25px_rgba(167,139,250,0.1)] transition-all duration-300 bg-[#111119] flex flex-col justify-between min-h-[320px]">
              <div>
                <div className="w-10 h-10 rounded-xl bg-[#a78bfa]/10 border border-[#a78bfa]/20 flex items-center justify-center text-[#a78bfa] mb-4">
                  <Code className="w-5 h-5" />
                </div>
                <h3 className="text-xl font-bold text-white font-heading mb-2">Repository Editing</h3>
                <p className="text-sm text-[#6b6b80] leading-relaxed font-body mb-6">
                  Upload or connect an existing repo. The Repository Agent indexes it into Qdrant, retrieves relevant context, and edits only what needs changing - without duplicating what you already have.
                </p>
              </div>
              <div className="pt-4 border-t border-[#1f1f2e] mt-auto">
                <div className="text-[10px] uppercase font-bold tracking-wider text-[#6b6b80] font-mono mb-2">
                  Pipeline Trace
                </div>
                <div className="text-[10px] sm:text-xs font-mono text-[#a78bfa] select-none bg-[#090910] px-2.5 py-1.5 rounded border border-[#1f1f2e] inline-block">
                  Repository Agent → Planner → Coder → Integrator
                </div>
              </div>
            </div>

            {/* Card 3 - Codebase Q&A */}
            <div className="card p-6 border border-[#1f1f2e] border-t-2 border-t-[#a78bfa]/30 hover:border-[#a78bfa] hover:shadow-[0_0_25px_rgba(167,139,250,0.1)] transition-all duration-300 bg-[#111119] flex flex-col justify-between min-h-[320px]">
              <div>
                <div className="w-10 h-10 rounded-xl bg-[#a78bfa]/10 border border-[#a78bfa]/20 flex items-center justify-center text-[#a78bfa] mb-4">
                  <Search className="w-5 h-5" />
                </div>
                <h3 className="text-xl font-bold text-white font-heading mb-2">Codebase Q&A</h3>
                <p className="text-sm text-[#6b6b80] leading-relaxed font-body mb-6">
                  Ask any question about a repository. The Explainer Agent retrieves semantically relevant code chunks and gives you architectural and logical answers grounded in your actual code.
                </p>
              </div>
              <div className="pt-4 border-t border-[#1f1f2e] mt-auto">
                <div className="text-[10px] uppercase font-bold tracking-wider text-[#6b6b80] font-mono mb-2">
                  Pipeline Trace
                </div>
                <div className="text-[10px] sm:text-xs font-mono text-[#a78bfa] select-none bg-[#090910] px-2.5 py-1.5 rounded border border-[#1f1f2e] inline-block">
                  Repository Agent → Explainer
                </div>
              </div>
            </div>
          </div>
        </div>



        {/* Comparison Table Section */}
        <div className="w-full max-w-5xl mx-auto mb-32 px-4 text-left">
          <div className="text-center mb-16">
            {/* <span className="text-xs font-mono font-bold tracking-widest text-[#00e5a0] uppercase px-3 py-1 rounded-full border border-[#00e5a0]/20 bg-[#00e5a0]/5">
              How It's Different
            </span> */}
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white mt-4 font-heading tracking-tight">
              Not a wrapper. An agent system built for production codebases.
            </h2>
          </div>

          <div className="overflow-x-auto rounded-2xl border border-[#1f1f2e] bg-[#111119]/35 backdrop-blur-md">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-[#1f1f2e] bg-[#090910]/80">
                  <th className="p-4 sm:p-5 font-heading font-extrabold text-white">Capability</th>
                  <th className="p-4 sm:p-5 font-heading font-semibold text-[#6b6b80]">Generic RAG / Chatbot</th>
                  <th className="p-4 sm:p-5 font-heading font-bold text-[#a78bfa] bg-[#a78bfa]/5">Adra-AI</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1f1f2e]/60 font-body">
                {/* Row 1 */}
                <tr>
                  <td className="p-4 sm:p-5 font-semibold text-white">Codebase awareness</td>
                  <td className="p-4 sm:p-5 text-[#6b6b80] font-light">
                    <span className="inline-flex items-center gap-1.5">
                      <X className="w-3.5 h-3.5 text-red-500/40 shrink-0" />
                      Sliding window context only
                    </span>
                  </td>
                  <td className="p-4 sm:p-5 text-[#a78bfa] font-medium bg-[#a78bfa]/5">
                    <span className="inline-flex items-center gap-1.5">
                      <Check className="w-4 h-4 shrink-0 text-[#a78bfa]" />
                      Full AST-parsed, semantically indexed repository
                    </span>
                  </td>
                </tr>
                {/* Row 2 */}
                <tr>
                  <td className="p-4 sm:p-5 font-semibold text-white">Indexing efficiency</td>
                  <td className="p-4 sm:p-5 text-[#6b6b80] font-light">
                    <span className="inline-flex items-center gap-1.5">
                      <X className="w-3.5 h-3.5 text-red-500/40 shrink-0" />
                      Re-embeds everything on each run
                    </span>
                  </td>
                  <td className="p-4 sm:p-5 text-[#a78bfa] font-medium bg-[#a78bfa]/5">
                    <span className="inline-flex items-center gap-1.5">
                      <Check className="w-4 h-4 shrink-0 text-[#a78bfa]" />
                      SHA256 hash-based incremental indexing - 90%+ cost reduction
                    </span>
                  </td>
                </tr>
                {/* Row 2.5 - Chunking Strategy */}
                <tr>
                  <td className="p-4 sm:p-5 font-semibold text-white">Chunking strategy</td>
                  <td className="p-4 sm:p-5 text-[#6b6b80] font-light">
                    <span className="inline-flex items-center gap-1.5">
                      <X className="w-3.5 h-3.5 text-red-500/40 shrink-0" />
                      Naive character counts (cuts functions and classes in half)
                    </span>
                  </td>
                  <td className="p-4 sm:p-5 text-[#a78bfa] font-medium bg-[#a78bfa]/5">
                    <span className="inline-flex items-center gap-1.5">
                      <Check className="w-4 h-4 shrink-0 text-[#a78bfa]" />
                      Supports 7+ languages with code-aware chunking (respects class & function boundaries)
                    </span>
                  </td>
                </tr>
                {/* Row 3 */}
                <tr>
                  <td className="p-4 sm:p-5 font-semibold text-white">Code structure</td>
                  <td className="p-4 sm:p-5 text-[#6b6b80] font-light">
                    <span className="inline-flex items-center gap-1.5">
                      <X className="w-3.5 h-3.5 text-red-500/40 shrink-0" />
                      One model, one pass
                    </span>
                  </td>
                  <td className="p-4 sm:p-5 text-[#a78bfa] font-medium bg-[#a78bfa]/5">
                    <span className="inline-flex items-center gap-1.5">
                      <Check className="w-4 h-4 shrink-0 text-[#a78bfa]" />
                      5 specialized LangGraph agents with typed state propagation
                    </span>
                  </td>
                </tr>

                {/* Row 5 */}
                <tr>
                  <td className="p-4 sm:p-5 font-semibold text-white">Cross-file consistency</td>
                  <td className="p-4 sm:p-5 text-[#6b6b80] font-light">
                    <span className="inline-flex items-center gap-1.5">
                      <X className="w-3.5 h-3.5 text-red-500/40 shrink-0" />
                      No cross-file validation
                    </span>
                  </td>
                  <td className="p-4 sm:p-5 text-[#a78bfa] font-medium bg-[#a78bfa]/5">
                    <span className="inline-flex items-center gap-1.5">
                      <Check className="w-4 h-4 shrink-0 text-[#a78bfa]" />
                      Integrator agent does a full codebase validation pass post-generation
                    </span>
                  </td>
                </tr>
                {/* Row 6 */}
                <tr>
                  <td className="p-4 sm:p-5 font-semibold text-white">Real-time visibility</td>
                  <td className="p-4 sm:p-5 text-[#6b6b80] font-light">
                    <span className="inline-flex items-center gap-1.5">
                      <X className="w-3.5 h-3.5 text-red-500/40 shrink-0" />
                      Spinner until done
                    </span>
                  </td>
                  <td className="p-4 sm:p-5 text-[#a78bfa] font-medium bg-[#a78bfa]/5">
                    <span className="inline-flex items-center gap-1.5">
                      <Check className="w-4 h-4 shrink-0 text-[#a78bfa]" />
                      WebSocket-streamed per-agent execution logs to UI in real time
                    </span>
                  </td>
                </tr>
                {/* Row 7 */}
                <tr>
                  <td className="p-4 sm:p-5 font-semibold text-white">Multi-tenancy</td>
                  <td className="p-4 sm:p-5 text-[#6b6b80] font-light">
                    <span className="inline-flex items-center gap-1.5">
                      <X className="w-3.5 h-3.5 text-red-500/40 shrink-0" />
                      Single-user demo
                    </span>
                  </td>
                  <td className="p-4 sm:p-5 text-[#a78bfa] font-medium bg-[#a78bfa]/5">
                    <span className="inline-flex items-center gap-1.5">
                      <Check className="w-4 h-4 shrink-0 text-[#a78bfa]" />
                      PostgreSQL-backed user isolation with OAuth and project management
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Tech Stack Section */}
        <div className="w-full max-w-5xl mx-auto mb-24 px-4 text-left">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white font-heading tracking-tight">
              Built on production-grade tooling.
            </h2>
            <p className="text-base text-[#6b6b80] mt-3 font-body">
              No toy demos. Every library chosen for a specific architectural reason.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              {
                name: "LangGraph",
                role: "Agent orchestration",
                desc: "Manages cyclic graphs, loops, and agent shared state with full conditional branching controls.",
                icon: <Workflow className="w-5 h-5 text-[#a78bfa]" />,
              },
              {
                name: "Qdrant",
                role: "Vector store + RAG",
                desc: "Dense semantic matching engine. Stores code node AST chunks and performs hybrid text search.",
                icon: <Database className="w-5 h-5 text-[#00e5a0]" />,
              },
              {
                name: "FastAPI",
                role: "Async REST + WebSocket",
                desc: "High-performance Python backend coordinating state transfers and streaming real-time agent logs.",
                icon: <Server className="w-5 h-5 text-[#4cc2e9]" />,
              },
              {
                name: "Next.js 14",
                role: "Frontend App Router",
                desc: "React server components render fast layouts. Handles auth and streams WebSocket updates.",
                icon: <Layers className="w-5 h-5 text-[#a78bfa]" />,
              },
              {
                name: "Gemini 2.5 Flash",
                role: "Primary LLM",
                desc: "High token context limits with extremely low inference speeds for repository ingestion.",
                icon: <Cpu className="w-5 h-5 text-[#00e5a0]" />,
              },
              {
                name: "PostgreSQL",
                role: "Multi-tenant persistence",
                desc: "Holds workspace, users, and execution logs. Built with transactional safety guarantees.",
                icon: <Database className="w-5 h-5 text-[#4cc2e9]" />,
              },
              {
                name: "Docker",
                role: "Containerized deploy",
                desc: "Guarantees reproducible runtime execution across local, staging, and production environments.",
                icon: <Boxes className="w-5 h-5 text-[#a78bfa]" />,
              },
              {
                name: "OAuth 2.0",
                role: "Google + GitHub auth",
                desc: "Secure multi-tenant credentials mapping workspace access to team repository nodes.",
                icon: <Lock className="w-5 h-5 text-[#00e5a0]" />,
              },
            ].map((tech, i) => (
              <div
                key={i}
                className="card p-5 border border-[#1f1f2e] bg-[#111119] hover:border-[#a78bfa]/40 transition-all duration-200 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] uppercase font-bold tracking-wider text-[#6b6b80] font-mono">
                      {tech.role}
                    </span>
                    {tech.icon}
                  </div>
                  <h4 className="text-base font-bold text-white font-heading mb-1.5">
                    {tech.name}
                  </h4>
                  <p className="text-xs text-[#6b6b80] leading-relaxed font-body">
                    {tech.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer
        className="relative z-10 text-center py-8 text-xs border-t"
        style={{ color: "#6b6b80", borderColor: "#1f1f2e", background: "#090910" }}
      >
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <span>© {new Date().getFullYear()} Adra-AI</span>
          {/* <span className="hidden sm:inline">•</span>
          <a
            href="https://github.com/adityaxxz/Adra-AI"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all duration-200 text-zinc-300 hover:text-white bg-zinc-950/40 hover:bg-violet-950/20 border-zinc-800 hover:border-violet-500/40 hover:shadow-[0_0_12px_rgba(167,139,250,0.15)]"
          >
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
              <path
                fillRule="evenodd"
                clipRule="evenodd"
                d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.464-1.11-1.464-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.579.688.481C19.138 20.161 22 16.416 22 12c0-5.523-4.477-10-10-10z"
              />
            </svg>
            <span>View Source Code</span>
          </a> */}
        </div>
      </footer>
    </div>
  );
}
