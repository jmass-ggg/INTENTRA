import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { CaretDown } from "@phosphor-icons/react";
import ConversationView from "./views/ConversationView";
import CommunicateView from "./views/CommunicateView";
import TeachIntentraView from "./views/TeachIntentraView";
import PassportView from "./views/PassportView";
import { DUR, EASE_OUT } from "./lib/motion";
import logoMark from "./assets/logo-mark.png";

const NAV_ITEMS = [
  { to: "/communicate", label: "Communicate", end: false },
  { to: "/passport", label: "Passport", end: false },
  { to: "/teach", label: "Teach", end: false },
];

function TopBar() {
  return (
    <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-ink-line bg-ink px-4 py-2.5 sm:px-6">
      {/* Brand — the Intentra head mark (assets/logo-mark.png) + wordmark. */}
      <div className="flex items-center gap-2.5" aria-label="Intentra">
        <img
          src={logoMark}
          alt=""
          aria-hidden
          className="h-8 w-auto shrink-0 sm:h-9"
        />
        <span
          className="whitespace-nowrap leading-none tracking-[-0.01em]"
          style={{ fontFamily: '"Quicksand", ui-sans-serif, system-ui, sans-serif' }}
        >
          <span className="text-[1.35rem] font-bold text-[#0E3A42] sm:text-[1.5rem]">
            Intentra
          </span>
        </span>
      </div>

      {/* Person switcher (hidden on the narrowest screens to keep one row). */}
      <button
        type="button"
        aria-label="Switch person — current: Elena"
        className="ml-1 hidden h-10 items-center gap-1.5 rounded-full border border-ink-line bg-ink-raised px-3.5 font-ui text-[0.95rem] font-medium text-text transition-colors duration-fast ease-out-quart hover:bg-ink-sunken sm:inline-flex"
      >
        Elena
        <CaretDown size={14} weight="bold" aria-hidden className="text-text-muted" />
      </button>

      {/* Quiet pill nav. */}
      <nav className="ml-auto flex items-center gap-1.5 sm:gap-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              [
                "inline-flex h-10 items-center justify-center rounded-full px-4 font-ui text-[0.95rem] font-medium transition-colors duration-fast ease-out-quart",
                isActive
                  ? "bg-ink-raised text-text shadow-card ring-1 ring-ink-line"
                  : "text-text-muted hover:bg-ink-sunken hover:text-text",
              ].join(" ")
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Honest status chip — non-interactive (hidden below lg). */}
      <div
        role="status"
        className="hidden h-10 items-center gap-2 rounded-full border border-transparent bg-ink-sunken px-3.5 lg:inline-flex"
      >
        <span aria-hidden className="h-2 w-2 rounded-full bg-mind" />
        <span className="font-mono text-[0.72rem] uppercase tracking-[0.1em] text-text-muted">
          on-device · airplane-ok
        </span>
      </div>
    </header>
  );
}

export default function App() {
  const location = useLocation();

  return (
    // reducedMotion="user" makes every Framer Motion component honor the OS
    // "reduce motion" setting (disables transform/layout animation, keeps
    // opacity) — covers the candidate bloom + selection choreography that CSS
    // alone can't reach.
    <MotionConfig reducedMotion="user">
    <div className="flex h-full flex-col bg-ink text-text">
      <TopBar />
      <main className="flex-1 overflow-auto">
        {/* Light-touch route transitions. */}
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: DUR.fast, ease: EASE_OUT }}
            style={{ height: "100%" }}
          >
            <Routes location={location}>
              <Route path="/" element={<Navigate to="/communicate" replace />} />
              <Route path="/communicate" element={<CommunicateView />} />
              <Route path="/teach" element={<TeachIntentraView />} />
              <Route path="/conversation" element={<ConversationView />} />
              <Route path="/passport" element={<PassportView />} />
              <Route path="/graph" element={<Navigate to="/passport" replace />} />
            </Routes>
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
    </MotionConfig>
  );
}
