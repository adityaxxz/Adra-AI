import Link from "next/link";
import dynamic from "next/dynamic";

const Orb = dynamic(() => import("@/components/Orb"), { ssr: false });


export default function Home() {
  return (
    <div
      className="min-h-screen flex flex-col relative overflow-hidden"
      style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}
    >
      {/* Animated background orbs */}
      <div className="absolute inset-0 z-0 pointer-events-none opacity-45">
        <Orb
          hoverIntensity={1.5}
          rotateOnHover={true}
          hue={0}
          forceHoverState={false}
          backgroundColor="#0a0a0f"
        />
      </div>

      {/* Navigation */}
      <nav
        className="relative z-10 flex items-center justify-between px-8 py-4 border-b"
        style={{ borderColor: 'var(--border)', background: 'rgba(10,10,15,0.8)', backdropFilter: 'blur(16px)' }}
      >
        <div className="flex items-center gap-3">
          <img src="/logo.png" alt="Adra-AI" className="w-8 h-8 rounded-lg object-contain" />
          <span className="text-base font-bold text-white tracking-tight">Adra-AI</span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/auth/signin"
            className="btn-secondary text-sm"
            id="sign-in-nav"
          >
            Sign In
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 pt-10 pb-12 text-center">
        {/* Badge */}
        <div
          className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium mb-5 animate-fade-in"
          style={{
            background: 'rgba(139,92,246,0.1)',
            border: '1px solid rgba(139,92,246,0.25)',
            color: '#a78bfa',
          }}
        >
          <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
          AI-Powered Codebase Intelligence
        </div>

        {/* Headline */}
        <h1
          className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white tracking-tighter leading-[1.05] mb-4 animate-fade-in-up"
          style={{ letterSpacing: '-0.04em' }}
        >
          Build smarter
          <br />
          <span className="gradient-text">with AI agents</span>
        </h1>

        {/* Subheadline */}
        <p
          className="text-sm sm:text-base max-w-xl mx-auto mb-6 leading-relaxed animate-fade-in-up delay-100"
          style={{ color: 'var(--text-secondary)' }}
        >
          Generate full-stack applications, edit existing repositories, and get intelligent code
          assistance — all powered by advanced AI agents that understand your codebase.
        </p>

        {/* CTA */}
        <div className="flex flex-col sm:flex-row items-center gap-4 mb-8 animate-fade-in-up delay-200">
          <Link
            href="/auth/signin"
            className="btn-primary text-sm glow-btn"
            id="hero-cta"
          >
            Start Building Free
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </Link>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            No credit card required
          </p>
        </div>

        {/* Feature Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-5xl w-full animate-fade-in-up delay-300">
          {[
            {
              icon: (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              ),
              color: '#8b5cf6',
              colorBg: 'rgba(139,92,246,0.1)',
              colorBorder: 'rgba(139,92,246,0.2)',
              title: 'Project Generation',
              desc: 'Generate complete full-stack applications from a natural language description in seconds.',
            },
            {
              icon: (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              ),
              color: '#6366f1',
              colorBg: 'rgba(99,102,241,0.1)',
              colorBorder: 'rgba(99,102,241,0.2)',
              title: 'Repository Editing',
              desc: 'Upload your existing codebase and let AI make intelligent edits across multiple files.',
            },
            {
              icon: (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              ),
              color: '#3b82f6',
              colorBg: 'rgba(59,130,246,0.1)',
              colorBorder: 'rgba(59,130,246,0.2)',
              title: 'Code Understanding',
              desc: 'Ask questions about any codebase and receive accurate, context-aware answers instantly.',
            },
          ].map((feature, i) => (
            <div
              key={i}
              className="card p-5 text-left card-hover"
              style={{ background: 'rgba(17,17,24,0.7)', backdropFilter: 'blur(12px)' }}
            >
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center mb-3"
                style={{ background: feature.colorBg, border: `1px solid ${feature.colorBorder}`, color: feature.color }}
              >
                {feature.icon}
              </div>
              <h3 className="text-base font-semibold text-white mb-1.5">{feature.title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {feature.desc}
              </p>
            </div>
          ))}
        </div>

        {/* Stats row */}
        {/* <div
          className="flex flex-wrap items-center justify-center gap-10 mt-16 animate-fade-in-up delay-400"
          style={{ color: 'var(--text-muted)' }}
        >
          {[
            { value: 'Multi-file', label: 'Edits in one shot' },
            { value: 'Full-stack', label: 'App generation' },
            { value: 'Real-time', label: 'AI streaming' },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <p className="text-2xl font-bold text-white mb-0.5">{stat.value}</p>
              <p className="text-xs">{stat.label}</p>
            </div>
          ))}
        </div> */}
      </main>

      {/* Footer */}
      <footer
        className="relative z-10 text-center py-4 text-xs border-t"
        style={{ color: 'var(--text-muted)', borderColor: 'var(--border)' }}
      >
        <div className="flex flex-col sm:flex-row items-center justify-center gap-2">
          <span>© {new Date().getFullYear()} Adra-AI</span>
          <span className="hidden sm:inline">•</span>
          <a
            href="https://github.com/adityaxxz/Adra-AI"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all duration-200 text-zinc-300 hover:text-white bg-zinc-950/40 hover:bg-violet-950/20 border-zinc-800 hover:border-violet-500/40 hover:shadow-[0_0_12px_rgba(139,92,246,0.15)]"
          >
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
              <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.464-1.11-1.464-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.579.688.481C19.138 20.161 22 16.416 22 12c0-5.523-4.477-10-10-10z" />
            </svg>
            <span>View Source Code</span>
          </a>
        </div>
      </footer>
    </div>
  );
}
