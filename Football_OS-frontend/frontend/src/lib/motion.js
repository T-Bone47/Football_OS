// Single entry point for animation. framer-motion is the same library Motion
// now publishes as `motion`; switching later means changing this import only.
export { motion, AnimatePresence, MotionConfig, LayoutGroup, useReducedMotion, animate } from "framer-motion";

// Subtle by design: this is an operations tool. Movement never exceeds 8 px.
export const duration = { fast: 0.15, base: 0.22, slow: 0.35 };
export const ease = [0.22, 1, 0.36, 1];
export const spring = { type: "spring", stiffness: 520, damping: 40, mass: 0.8 };

export const fade = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: duration.base, ease } },
  exit: { opacity: 0, transition: { duration: duration.fast, ease } },
};

export const fadeUp = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: { duration: duration.base, ease } },
  exit: { opacity: 0, y: -4, transition: { duration: duration.fast, ease } },
};

export const pop = {
  initial: { opacity: 0, scale: 0.98, y: -4 },
  animate: { opacity: 1, scale: 1, y: 0, transition: { duration: duration.base, ease } },
  exit: { opacity: 0, scale: 0.98, transition: { duration: duration.fast, ease } },
};

export const stagger = (step = 0.04, delay = 0) => ({
  initial: {},
  animate: { transition: { staggerChildren: step, delayChildren: delay } },
});

// Variant for children of a `stagger` container (no own initial/animate props).
export const item = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: { duration: duration.base, ease } },
};
