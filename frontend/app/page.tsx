"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Sparkles,
  Code,
  Search,
  Check,
  X,
  ArrowRight,
  Terminal,
  Cpu,
  Layers,
  Workflow,
  Server,
  Lock,
  Database,
  Boxes,
} from "lucide-react";
import { ThemeToggle } from "../components/ThemeToggle";

const GITHUB_URL = "https://github.com/adityaxxz/Adra-AI";

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

// The trace sits on a dark terminal in both themes, so these colours are fixed.
const AGENT_BADGE: Record<string, string> = {
  planner: "bg-[rgba(129,140,248,0.12)] text-[#a5b4fc] border-[rgba(129,140,248,0.25)]",
  architect: "bg-[rgba(52,211,153,0.12)] text-[#6ee7b7] border-[rgba(52,211,153,0.25)]",
  coder: "bg-[rgba(96,165,250,0.12)] text-[#93c5fd] border-[rgba(96,165,250,0.25)]",
  integrator: "bg-[rgba(248,113,113,0.12)] text-[#fca5a5] border-[rgba(248,113,113,0.25)]",
  done: "bg-[rgba(52,211,153,0.16)] text-[#6ee7b7] border-[rgba(52,211,153,0.35)] font-semibold",
};

const METRICS = [
  { value: "90%+", label: "Indexing cost reduction", note: "from SHA256 incremental indexing" },
  { value: "7+", label: "Languages supported", note: "including Python, TS, JS, Go" },
  { value: "5", label: "Specialized agents", note: "in a LangGraph StateGraph" },
  { value: "3", label: "Operation modes", note: "Build, Edit, or Q&A" },
];

const MODES = [
  {
    icon: <Sparkles className="w-5 h-5" />,
    title: "Project Generation",
    desc: "Describe your app in plain English. Adra-AI plans the architecture, orders the files by dependency, writes each one with cross-file context, and validates the whole codebase before handing it to you.",
    trace: "Planner → Architect → Coder → Integrator",
  },
  {
    icon: <Code className="w-5 h-5" />,
    title: "Repository Editing",
    desc: "Upload or connect an existing repo. The Repository Agent indexes it into Qdrant, and the Edit Planner picks only the files that need changing, grounded in your real file tree. The Coder applies each edit, the Integrator checks just those files, and you accept or reject every change as a diff.",
    trace: "Repository Agent → Edit Planner → Coder → Integrator",
  },
  {
    icon: <Search className="w-5 h-5" />,
    title: "Codebase Q&A",
    desc: "Ask any question about a repository. The Explainer Agent retrieves semantically relevant code chunks and gives you architectural and logical answers grounded in your actual code.",
    trace: "Repository Agent → Explainer",
  },
];

const COMPARISON = [
  ["Codebase awareness", "Sliding window context only", "Full AST-parsed, semantically indexed repository"],
  ["Indexing efficiency", "Re-embeds everything on each run", "SHA256 hash-based incremental indexing - 90%+ cost reduction"],
  ["Chunking strategy", "Naive character counts (cuts functions and classes in half)", "Supports 7+ languages with code-aware chunking (respects class & function boundaries)"],
  ["Code structure", "One model, one pass", "5 specialized LangGraph agents with typed state propagation"],
  ["Cross-file consistency", "No cross-file validation", "Integrator agent does a full codebase validation pass post-generation"],
  ["Real-time visibility", "Spinner until done", "WebSocket-streamed per-agent execution logs to UI in real time"],
  ["Multi-tenancy", "Single-user demo", "PostgreSQL-backed user isolation with OAuth and project management"],
];

const STACK = [
  { name: "LangGraph", role: "Agent orchestration", desc: "Manages cyclic graphs, loops, and agent shared state with full conditional branching controls.", icon: Workflow },
  { name: "Qdrant", role: "Vector store + RAG", desc: "Dense semantic matching engine. Stores code node AST chunks and performs hybrid text search.", icon: Database },
  { name: "FastAPI", role: "Async REST + WebSocket", desc: "High-performance Python backend coordinating state transfers and streaming real-time agent logs.", icon: Server },
  { name: "Next.js 14", role: "Frontend App Router", desc: "React server components render fast layouts. Handles auth and streams WebSocket updates.", icon: Layers },
  { name: "Gemini + Groq API Models", role: "Primary LLM", desc: "High token context limits with extremely low inference speeds for repository ingestion.", icon: Cpu },
  { name: "PostgreSQL", role: "Multi-tenant persistence", desc: "Holds workspace, users, and execution logs. Built with transactional safety guarantees.", icon: Database },
  { name: "Docker", role: "Containerized deploy", desc: "Guarantees reproducible runtime execution across local, staging, and production environments.", icon: Boxes },
  { name: "OAuth 2.0", role: "Google + GitHub auth", desc: "Secure multi-tenant credentials mapping workspace access to team repository nodes.", icon: Lock },
];

function GitHubIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={`${className} fill-current`} viewBox="0 0 24 24" aria-hidden="true">
      <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.464-1.11-1.464-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.579.688.481C19.138 20.161 22 16.416 22 12c0-5.523-4.477-10-10-10z" />
    </svg>
  );
}

function SectionHeading({ title }: { title: string }) {
  return (
    <div className="text-center mb-12">
      <h2 className="text-3xl sm:text-4xl font-bold text-fg tracking-tight text-balance">{title}</h2>
    </div>
  );
}

export default function Home() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(0);
  const terminalContainerRef = useRef<HTMLDivElement>(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      setIsLoggedIn(true);
      router.push("/dashboard");
    }
  }, [router]);

  useEffect(() => {
    // Listen for storage changes to update login state across tabs
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === "token") {
        const loggedIn = !!e.newValue;
        setIsLoggedIn(loggedIn);
        if (loggedIn) {
          router.push("/dashboard");
        }
      }
    };
    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, [router]);

  useEffect(() => {
    const timer = setTimeout(
      () => setCurrentStep((prev) => (prev < TERMINAL_STEPS.length - 1 ? prev + 1 : 0)),
      currentStep < TERMINAL_STEPS.length - 1 ? 450 : 4000
    );
    return () => clearTimeout(timer);
  }, [currentStep]);

  useEffect(() => {
    if (terminalContainerRef.current) {
      terminalContainerRef.current.scrollTop = terminalContainerRef.current.scrollHeight;
    }
  }, [currentStep]);

  const primaryCta = isLoggedIn
    ? { href: "/dashboard", label: "View Your Dashboard", id: "hero-cta-dashboard" }
    : { href: "/auth/signin", label: "Start Building Free", id: "hero-cta-start" };

  return (
    <div className="min-h-screen flex flex-col bg-canvas text-fg font-body">
      {/* Navigation */}
      <nav className="sticky top-0 z-30 border-b border-line" style={{ background: "var(--nav-bg)", backdropFilter: "blur(16px)" }}>
        <div className="max-w-6xl mx-auto flex items-center justify-between px-6 h-16">
          <Link href="/" className="flex items-center gap-2.5">
            <img src="/logo.png" alt="Adra-AI" className="w-8 h-8 rounded-lg object-contain" />
            <span className="text-base font-bold tracking-tight font-heading">Adra-AI</span>
          </Link>
          <div className="flex items-center gap-2">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost"
              aria-label="Adra-AI on GitHub"
            >
              <GitHubIcon />
              <span>GitHub</span>
            </a>
            <ThemeToggle />
          </div>
        </div>
      </nav>

      <main className="flex-1">
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div
            className="absolute left-1/2 top-[-180px] -translate-x-1/2 w-[900px] h-[520px] rounded-full pointer-events-none"
            style={{ background: "radial-gradient(closest-side, var(--hero-glow), transparent)" }}
          />
          <div className="relative max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-[1.08] text-balance">
              Your codebase has context.
              <br />
              Most AI agents ignore it.
              <br />
              <span className="text-accent">Adra-AI doesn&apos;t.</span>
            </h1>
            <p className="mt-6 text-base sm:text-lg max-w-2xl mx-auto leading-relaxed text-fg-secondary">
              Adra-AI is a multi-agent coding intelligence platform that reads, indexes, and reasons over your entire repository before writing a single line of code - so generated code actually fits what you already built.
            </p>
            <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link href={primaryCta.href} className="btn-primary w-full sm:w-auto px-6 py-3" id={primaryCta.id}>
                {primaryCta.label}
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>

          {/* Metrics */}
          <div className="relative max-w-5xl mx-auto px-6 pb-20">
            <div className="card overflow-hidden grid grid-cols-2 lg:grid-cols-4 gap-px bg-line">
              {METRICS.map((m) => (
                <div key={m.label} className="p-6 text-center bg-surface">
                  <div className="text-3xl font-bold text-accent font-heading tracking-tight">{m.value}</div>
                  <div className="text-sm font-semibold mt-1.5">{m.label}</div>
                  <div className="text-xs text-fg-muted mt-1">{m.note}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Live agent trace */}
        <section className="max-w-4xl mx-auto px-6 pb-28">
          <SectionHeading title="Every agent step, streamed live." />
          <div className="rounded-2xl overflow-hidden" style={{ background: "var(--code-bg)", border: "1px solid var(--code-border)", boxShadow: "var(--shadow-lg)" }}>
            <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--code-border)", background: "var(--code-header-bg)" }}>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-full bg-[#ef4444]/80" />
                <span className="w-3 h-3 rounded-full bg-[#facc15]/80" />
                <span className="w-3 h-3 rounded-full bg-[#22c55e]/80" />
              </div>
              <div className="text-xs font-mono select-none flex items-center gap-1.5" style={{ color: "var(--code-muted)" }}>
                <Terminal className="w-3.5 h-3.5 text-[#a5b4fc]" />
                agent_execution_trace.sh
              </div>
              <div className="w-12" />
            </div>
            <div ref={terminalContainerRef} className="p-6 overflow-y-auto h-[380px] scrollbar-hide select-none">
              <div className="font-mono text-left space-y-3 text-xs sm:text-sm">
                {TERMINAL_STEPS.slice(0, currentStep + 1).map((step, idx) => (
                  <div key={idx} className="flex flex-col sm:flex-row sm:items-start gap-2 sm:gap-3 py-1 animate-fade-in">
                    <span className={`inline-block px-2.5 py-0.5 rounded text-[10px] uppercase font-bold border tracking-wider text-center w-[96px] shrink-0 ${AGENT_BADGE[step.agent]}`}>
                      {step.agent}
                    </span>
                    <span className="leading-relaxed" style={{ color: "var(--code-fg)" }}>{step.text}</span>
                  </div>
                ))}
                {currentStep < TERMINAL_STEPS.length - 1 ? (
                  <div className="flex items-center gap-2 text-[#a5b4fc] text-xs pt-2 animate-pulse">
                    <span className="w-1.5 h-3 bg-[#a5b4fc]" />
                    <span>Agent execution in progress...</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-[#6ee7b7] text-xs pt-4">
                    <Check className="w-4 h-4" />
                    <span>Trace execution completed.</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* Modes */}
        <section className="max-w-6xl mx-auto px-6 pb-28">
          <SectionHeading title="Three modes. One intelligent platform." />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {MODES.map((mode) => (
              <div key={mode.title} className="card card-hover p-6 flex flex-col">
                <div className="icon-tile mb-5">{mode.icon}</div>
                <h3 className="text-lg font-semibold mb-2">{mode.title}</h3>
                <p className="text-sm text-fg-secondary leading-relaxed mb-6">{mode.desc}</p>
                <div className="mt-auto pt-4 border-t border-line">
                  <div className="text-[10px] uppercase font-semibold tracking-wider text-fg-muted mb-2">Pipeline trace</div>
                  <div className="text-xs font-mono text-accent bg-subtle px-2.5 py-1.5 rounded-md border border-line inline-block">
                    {mode.trace}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Comparison */}
        <section className="max-w-5xl mx-auto px-6 pb-28">
          <SectionHeading title="Not a wrapper. An agent system built for production codebases." />
          <div className="card overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-line bg-subtle">
                  <th className="p-4 sm:p-5 font-semibold">Capability</th>
                  <th className="p-4 sm:p-5 font-semibold text-fg-muted">Generic RAG / Chatbot</th>
                  <th className="p-4 sm:p-5 font-semibold text-accent bg-accent-soft">Adra-AI</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {COMPARISON.map(([capability, generic, ours]) => (
                  <tr key={capability}>
                    <td className="p-4 sm:p-5 font-medium">{capability}</td>
                    <td className="p-4 sm:p-5 text-fg-muted">
                      <span className="inline-flex items-start gap-2">
                        <X className="w-4 h-4 shrink-0 mt-0.5 text-danger opacity-60" />
                        {generic}
                      </span>
                    </td>
                    <td className="p-4 sm:p-5 bg-accent-soft">
                      <span className="inline-flex items-start gap-2">
                        <Check className="w-4 h-4 shrink-0 mt-0.5 text-accent" />
                        {ours}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Stack */}
        <section className="max-w-6xl mx-auto px-6 pb-28">
          <SectionHeading title="Built on production-grade tooling." />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {STACK.map(({ name, role, desc, icon: Icon }) => (
              <div key={name} className="card card-hover p-5">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-[10px] uppercase font-semibold tracking-wider text-fg-muted">{role}</span>
                  <Icon className="w-5 h-5 text-accent" />
                </div>
                <h4 className="text-base font-semibold font-heading mb-1.5">{name}</h4>
                <p className="text-xs text-fg-secondary leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </section>

      </main>

      {/* Footer */}
      <footer className="border-t border-line">
        <div className="max-w-6xl mx-auto px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-fg-muted">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="" className="w-5 h-5 rounded object-contain" />
            <span>© {new Date().getFullYear()} Adra-AI</span>
          </div>
          <span>
            Made by{" "}
            <a href="https://adxra.me" target="_blank" rel="noopener noreferrer" className="font-medium text-fg-secondary hover:text-accent transition-colors">
              Adra
            </a>
          </span>
        </div>
      </footer>
    </div>
  );
}
