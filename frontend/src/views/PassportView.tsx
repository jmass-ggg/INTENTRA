// PassportView — Communication Passport UI
//
// Displays the user's linguistic identity, vocabulary, preferences, people,
// and communication rules in a readable, accessible format. No graph
// visualization — plain layout with large touch targets and keyboard navigation.

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  User,
  ChatCircle,
  ThumbsUp,
  ThumbsDown,
  SpeakerHigh,
  Heart,
  WarningCircle,
} from "@phosphor-icons/react";
import { getPassport, type CommunicationPassport, type PersonProfile } from "../lib/api";
import { DUR, EASE_OUT } from "../lib/motion";

// Matches the demo persona
const PERSON_ID = "elena";

interface SectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  isEmpty?: boolean;
}

function Section({ title, icon, children, isEmpty }: SectionProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: DUR.base, ease: EASE_OUT }}
      className="rounded-xl border border-ink-line bg-ink-raised p-5 shadow-card sm:p-6"
    >
      <div className="mb-4 flex items-center gap-3">
        <div
          aria-hidden
          className="flex h-10 w-10 items-center justify-center rounded-full bg-voice-soft text-voice"
        >
          {icon}
        </div>
        <h2 className="m-0 font-ui text-aac-lg font-semibold text-text">{title}</h2>
      </div>

      {isEmpty ? (
        <p className="m-0 font-ui text-aac-base text-text-muted italic">
          No information added yet. Use Teach Intentra to build this section.
        </p>
      ) : (
        <div className="flex flex-col gap-3">{children}</div>
      )}
    </motion.section>
  );
}

function PersonCard({ person }: { person: PersonProfile }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-ink-line bg-ink-sunken p-3 transition-colors duration-fast hover:bg-ink">
      <div
        aria-hidden
        className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-voice/30 bg-voice-soft text-voice-deep font-mono text-[1.1rem] font-semibold"
      >
        {person.name.charAt(0).toUpperCase()}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="font-ui text-aac-base font-medium text-text">{person.name}</span>
        {person.relationship && (
          <span className="eyebrow text-text-muted">{person.relationship}</span>
        )}
        {person.address_term && (
          <span className="font-mono text-[0.8rem] text-text-faint">
            I call them: "{person.address_term}"
          </span>
        )}
      </div>
    </div>
  );
}

function ItemList({ items, emptyMessage }: { items: string[]; emptyMessage?: string }) {
  if (items.length === 0) {
    return (
      <p className="m-0 font-ui text-aac-base text-text-muted italic">
        {emptyMessage || "None added yet."}
      </p>
    );
  }

  return (
    <ul className="m-0 grid list-none gap-2 p-0 sm:grid-cols-2">
      {items.map((item, i) => (
        <li
          key={i}
          className="flex items-start gap-2 rounded-lg border border-ink-line bg-ink-sunken px-3 py-2.5"
        >
          <span aria-hidden className="mt-0.5 text-voice">
            •
          </span>
          <span className="flex-1 font-ui text-aac-base text-text leading-snug">{item}</span>
        </li>
      ))}
    </ul>
  );
}

export default function PassportView() {
  const [passport, setPassport] = useState<CommunicationPassport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);

    getPassport(PERSON_ID)
      .then((data) => {
        if (alive) {
          setPassport(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (alive) {
          setError(String(err));
          setLoading(false);
        }
      });

    return () => {
      alive = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
            aria-hidden
            className="text-voice"
          >
            <ChatCircle size={48} weight="duotone" />
          </motion.div>
          <p className="m-0 font-ui text-aac-base text-text-muted">
            Loading Communication Passport…
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="flex max-w-md flex-col items-center gap-4 text-center">
          <div
            aria-hidden
            className="flex h-16 w-16 items-center justify-center rounded-full bg-ink-raised text-text-muted"
          >
            <WarningCircle size={40} weight="duotone" />
          </div>
          <h2 className="m-0 font-ui text-aac-lg font-semibold text-text">
            Couldn't load passport
          </h2>
          <p className="m-0 font-ui text-aac-base text-text-muted">{error}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-2 inline-flex h-12 items-center justify-center rounded-full border border-voice/30 bg-voice px-6 font-ui text-aac-base font-semibold text-on-voice shadow-card transition-colors duration-fast hover:bg-voice-deep"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (!passport) {
    return null;
  }

  return (
    <div className="h-full overflow-y-auto bg-ink">
      <div className="mx-auto max-w-5xl p-4 sm:p-6 lg:p-8">
        <motion.header
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: DUR.base, ease: EASE_OUT }}
          className="mb-6 sm:mb-8"
        >
          <h1 className="m-0 mb-2 font-ui text-[1.75rem] font-bold text-text sm:text-[2rem]">
            Communication Passport
          </h1>
          <p className="m-0 font-ui text-aac-base text-text-muted">
            Your linguistic identity, vocabulary, and preferences — always representing you
            authentically.
          </p>
        </motion.header>

        <div className="flex flex-col gap-5">
          <Section
            title="People"
            icon={<User size={24} weight="duotone" />}
            isEmpty={passport.people.length === 0}
          >
            {passport.people.length > 0 && (
              <div className="grid gap-3 sm:grid-cols-2">
                {passport.people.map((person) => (
                  <PersonCard key={person.id} person={person} />
                ))}
              </div>
            )}
          </Section>

          <Section
            title="How I Communicate"
            icon={<ChatCircle size={24} weight="duotone" />}
            isEmpty={passport.communication_rules.length === 0 && passport.routines.length === 0}
          >
            {passport.communication_rules.length > 0 && (
              <div>
                <h3 className="eyebrow mb-2">Communication Rules</h3>
                <ItemList items={passport.communication_rules} />
              </div>
            )}
            {passport.routines.length > 0 && (
              <div>
                <h3 className="eyebrow mb-2">Routines</h3>
                <ItemList items={passport.routines} />
              </div>
            )}
          </Section>

          <Section
            title="Words I Use"
            icon={<ThumbsUp size={24} weight="duotone" />}
            isEmpty={
              passport.vocabulary.length === 0 && passport.preferred_expressions.length === 0
            }
          >
            {passport.preferred_expressions.length > 0 && (
              <div>
                <h3 className="eyebrow mb-2">Preferred Expressions</h3>
                <ItemList items={passport.preferred_expressions} />
              </div>
            )}
            {passport.vocabulary.length > 0 && (
              <div>
                <h3 className="eyebrow mb-2">Vocabulary</h3>
                <div className="flex flex-wrap gap-2">
                  {passport.vocabulary.map((word, i) => (
                    <span
                      key={i}
                      className="inline-flex h-10 items-center justify-center rounded-full border border-ink-line bg-ink-sunken px-4 font-ui text-[0.95rem] text-text transition-colors duration-fast hover:bg-ink"
                    >
                      {word}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </Section>

          <Section
            title="Words I Avoid"
            icon={<ThumbsDown size={24} weight="duotone" />}
            isEmpty={passport.avoided_expressions.length === 0}
          >
            {passport.avoided_expressions.length > 0 && (
              <ItemList
                items={passport.avoided_expressions}
                emptyMessage="No avoided expressions — Intentra will never use these phrases."
              />
            )}
          </Section>

          <Section
            title="Emergency Communication"
            icon={<SpeakerHigh size={24} weight="duotone" />}
            isEmpty={passport.emergency_phrases.length === 0}
          >
            {passport.emergency_phrases.length > 0 && (
              <div className="flex flex-col gap-2">
                {passport.emergency_phrases.map((phrase, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 rounded-lg border-2 border-voice/40 bg-voice-soft p-4"
                  >
                    <Heart size={20} weight="fill" className="shrink-0 text-voice" aria-hidden />
                    <span className="flex-1 font-ui text-aac-base font-medium text-voice-deep">
                      {phrase}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>

        <motion.footer
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: DUR.base, ease: EASE_OUT, delay: 0.3 }}
          className="mt-8 rounded-lg border border-ink-line bg-ink-raised/60 p-4 text-center"
        >
          <p className="m-0 font-ui text-[0.9rem] text-text-muted">
            Use <strong className="text-text">Teach Intentra</strong> to build and update your
            Communication Passport.
          </p>
        </motion.footer>
      </div>
    </div>
  );
}
