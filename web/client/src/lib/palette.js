// Validated reference palette (light mode). Colour follows the entity, never its rank.
export const C = {
  blue: '#2a78d6', orange: '#eb6834', aqua: '#1baf7a', yellow: '#eda100',
  ink: '#0b0b0b', ink2: '#52514e', muted: '#898781', grid: '#e9e8e2', axis: '#c3c2b7',
};
export const STAGE_COLORS = { Prospecting: '#9ec5f4', Engaging: '#3987e5', Won: '#184f95', Lost: '#eb6834' };
export const OUTCOME_COLORS = { Won: '#2a78d6', Lost: '#eb6834', Open: '#b5b3ab' };
export const BLUE_RAMP = ['#f0efec', '#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95'];
export const rampColor = (t) => BLUE_RAMP[Math.max(0, Math.min(BLUE_RAMP.length - 1, Math.round(t * (BLUE_RAMP.length - 1))))];
