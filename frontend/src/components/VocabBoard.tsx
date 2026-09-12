// VocabBoard — categorized vocabulary tiles in the bottom well.
//
// AAC-correct tiles: a symbol (Phosphor duotone icon) sits above the word, the
// word always shown below for comprehension (color is never the only signal).
// People render as colored initial/icon avatars. Each category carries a calm
// accent hue applied to the icon + a thin top rule, on a light/white tile.
// Tiles lift on hover and press to 0.97; tap fires onTileTap(tile).

import type { ComponentType } from "react";
import { motion } from "framer-motion";
import {
  Snowflake,
  Bed,
  Smiley,
  ThumbsUp,
  Drop,
  Moon,
  HandPalm,
  Question,
  Check,
  X,
  Clock,
  FrameCorners,
  Baby,
  UsersThree,
  Heart,
  HandHeart,
  ChatCircle,
  type IconProps,
} from "@phosphor-icons/react";
import { DUR, EASE_OUT } from "../lib/motion";

export interface VocabTile {
  id: string;
  label: string;
}

export interface VocabCategory {
  id: string;
  label: string;
  tiles: VocabTile[];
}

export interface VocabBoardProps {
  onTileTap: (tile: VocabTile) => void;
  categories?: VocabCategory[];
}

type PhosphorIcon = ComponentType<IconProps>;

// Demo persona (Elena) vocabulary — covers all three demo rounds.
const DEMO_CATEGORIES: VocabCategory[] = [
  {
    id: "people",
    label: "People",
    tiles: [
      { id: "p-sofia", label: "Sofia" },
      { id: "p-mateo", label: "Mateo" },
      { id: "p-marco", label: "Marco" },
    ],
  },
  {
    id: "feelings",
    label: "Feelings",
    tiles: [
      { id: "f-tired", label: "tired" },
      { id: "f-cold", label: "cold" },
      { id: "f-happy", label: "happy" },
      { id: "f-okay", label: "okay" },
    ],
  },
  {
    id: "needs",
    label: "Needs",
    tiles: [
      { id: "n-window", label: "window" },
      { id: "n-water", label: "water" },
      { id: "n-rest", label: "rest" },
      { id: "n-help", label: "help" },
    ],
  },
  {
    id: "social",
    label: "Social",
    tiles: [
      { id: "s-maybe", label: "maybe" },
      { id: "s-yes", label: "yes" },
      { id: "s-no", label: "no" },
      { id: "s-later", label: "later" },
    ],
  },
];

// Per-category accent — calm hues used for the icon + a thin top rule, never as
// a saturated tile fill. People=coral, Feelings=indigo, Needs=teal, Social=warm.
interface CategoryStyle {
  icon: PhosphorIcon; // header icon
  iconText: string; // tile icon color
  iconWell: string; // tinted circle behind the symbol
  rule: string; // thin top accent rule
  hoverBorder: string; // hover ring tint
}

const CATEGORY_STYLE: Record<string, CategoryStyle> = {
  people: {
    icon: UsersThree,
    iconText: "text-voice",
    iconWell: "bg-voice-soft",
    rule: "bg-voice/55",
    hoverBorder: "hover:border-voice/45",
  },
  feelings: {
    icon: Heart,
    iconText: "text-register-neutral",
    iconWell: "bg-register-neutral/12",
    rule: "bg-register-neutral/50",
    hoverBorder: "hover:border-register-neutral/40",
  },
  needs: {
    icon: HandHeart,
    iconText: "text-mind",
    iconWell: "bg-mind-soft",
    rule: "bg-mind/50",
    hoverBorder: "hover:border-mind/45",
  },
  social: {
    icon: ChatCircle,
    iconText: "text-register-warm",
    iconWell: "bg-register-warm/12",
    rule: "bg-register-warm/50",
    hoverBorder: "hover:border-register-warm/40",
  },
};

const FALLBACK_STYLE: CategoryStyle = {
  icon: UsersThree,
  iconText: "text-text-muted",
  iconWell: "bg-ink-sunken",
  rule: "bg-ink-line",
  hoverBorder: "hover:border-voice/45",
};

// Word symbols — a sensible real Phosphor icon per vocabulary word.
const WORD_ICON: Record<string, PhosphorIcon> = {
  // Feelings
  "f-tired": Bed,
  "f-cold": Snowflake,
  "f-happy": Smiley,
  "f-okay": ThumbsUp,
  // Needs
  "n-window": FrameCorners, // window frame (no dedicated Window glyph in v2)
  "n-water": Drop,
  "n-rest": Moon,
  "n-help": HandPalm,
  // Social
  "s-maybe": Question,
  "s-yes": Check,
  "s-no": X,
  "s-later": Clock,
};

// People avatars — a per-person hue plus an initial (or a friendly icon for the
// 4-year-old grandson). Kept tasteful: soft tinted disc, no neon.
interface PersonAvatar {
  bg: string; // tinted disc
  fg: string; // initial / icon color
  icon?: PhosphorIcon; // optional icon instead of an initial
}

const PERSON_AVATAR: Record<string, PersonAvatar> = {
  "p-sofia": { bg: "bg-register-neutral/14", fg: "text-register-neutral" },
  "p-mateo": { bg: "bg-voice-soft", fg: "text-voice", icon: Baby },
  "p-marco": { bg: "bg-mind-soft", fg: "text-mind" },
};

const TILE_CLASS =
  "tile-base group relative overflow-hidden rounded-lg border border-ink-line bg-ink-raised px-3 py-3 text-text shadow-card transition-[border-color,box-shadow] duration-fast hover:shadow-lift";

export default function VocabBoard({
  onTileTap,
  categories = DEMO_CATEGORIES,
}: VocabBoardProps) {
  return (
    <div className="flex flex-col gap-7">
      {categories.map((category) => {
        const style = CATEGORY_STYLE[category.id] ?? FALLBACK_STYLE;
        const HeaderIcon = style.icon;
        const isPeople = category.id === "people";

        return (
          <section key={category.id} aria-label={category.label}>
            <h3 className="eyebrow mb-3 flex items-center gap-1.5">
              <HeaderIcon
                weight="duotone"
                size={16}
                className={style.iconText}
                aria-hidden
              />
              {category.label}
            </h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {category.tiles.map((tile) => {
                const person = isPeople ? PERSON_AVATAR[tile.id] : undefined;
                const WordIcon = WORD_ICON[tile.id];
                const AvatarIcon = person?.icon;

                return (
                  <motion.button
                    key={tile.id}
                    type="button"
                    whileHover={{ y: -3 }}
                    whileTap={{ scale: 0.97, y: 0 }}
                    transition={{ duration: DUR.fast, ease: EASE_OUT }}
                    onClick={() => onTileTap(tile)}
                    className={`${TILE_CLASS} ${style.hoverBorder}`}
                  >
                    {/* thin top accent rule (calm color coding, not a fill) —
                        inset so the rounded corners don't clip it to a notch. */}
                    <span
                      className={`pointer-events-none absolute inset-x-3 top-0 h-[3px] rounded-b-[2px] ${style.rule}`}
                      aria-hidden
                    />

                    {person ? (
                      // Person avatar: tinted disc with initial or friendly icon.
                      <span
                        className={`flex h-12 w-12 items-center justify-center rounded-full ${person.bg} ${person.fg}`}
                        aria-hidden
                      >
                        {AvatarIcon ? (
                          <AvatarIcon weight="duotone" size={28} />
                        ) : (
                          <span className="font-ui text-[1.6rem] font-semibold uppercase leading-none">
                            {tile.label.charAt(0)}
                          </span>
                        )}
                      </span>
                    ) : (
                      // Word symbol: tinted circle behind a duotone glyph.
                      <span
                        className={`flex h-12 w-12 items-center justify-center rounded-full ${style.iconWell} ${style.iconText}`}
                        aria-hidden
                      >
                        {WordIcon ? (
                          <WordIcon weight="duotone" size={30} />
                        ) : (
                          <Question weight="duotone" size={30} />
                        )}
                      </span>
                    )}

                    <span className="font-ui text-tile font-semibold leading-tight text-text">
                      {tile.label}
                    </span>
                  </motion.button>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
