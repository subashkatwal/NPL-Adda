/**
 * Original meme templates drawn on <canvas>: no third-party images, no image API.
 * Backgrounds are procedural and use the team's stored colours.
 */

const DEFAULT_TEAM = { primary_color: "#141C31", secondary_color: "#C8FF4D", short_name: "NPL" };
const FONT = (px) => `800 ${px}px "Barlow Condensed", "Noto Sans Devanagari", "Arial Narrow", sans-serif`;

/** Greedy word wrap; also breaks single words longer than the line. Pure for testing with a measure fn. */
export function wrapLines(measure, text, maxWidth) {
  const lines = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const candidate = line ? `${line} ${word}` : word;
    if (measure(candidate) <= maxWidth) {
      line = candidate;
      continue;
    }
    if (line) lines.push(line);
    if (measure(word) <= maxWidth) {
      line = word;
    } else {
      let chunk = "";
      for (const ch of word) {
        if (measure(chunk + ch) > maxWidth && chunk) {
          lines.push(chunk);
          chunk = ch;
        } else chunk += ch;
      }
      line = chunk;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/** Shrink the font until the caption fits in the box (max 6 lines). */
export function fitText(ctx, text, maxWidth, maxHeight, startPx) {
  for (let px = startPx; px >= 22; px -= 2) {
    ctx.font = FONT(px);
    const lines = wrapLines((s) => ctx.measureText(s).width, text, maxWidth);
    if (lines.length <= 6 && lines.length * px * 1.08 <= maxHeight) return { px, lines };
  }
  ctx.font = FONT(22);
  return { px: 22, lines: wrapLines((s) => ctx.measureText(s).width, text, maxWidth).slice(0, 6) };
}

function drawCaption(ctx, { text, x, y, width, height, align = "center", color = "#F5F7FA", startPx }) {
  const { px, lines } = fitText(ctx, text.toUpperCase(), width, height, startPx);
  ctx.textAlign = align;
  ctx.textBaseline = "top";
  ctx.lineJoin = "round";
  const lineHeight = px * 1.08;
  const top = y + (height - lines.length * lineHeight) / 2;
  lines.forEach((line, i) => {
    const ly = top + i * lineHeight;
    ctx.lineWidth = Math.max(4, px / 7);
    ctx.strokeStyle = "rgba(6, 9, 20, 0.85)";
    ctx.strokeText(line, x, ly);
    ctx.fillStyle = color;
    ctx.fillText(line, x, ly);
  });
}

const BACKGROUNDS = {
  scoreboard(ctx, s, team) {
    ctx.fillStyle = "#0B1020";
    ctx.fillRect(0, 0, s, s);
    ctx.fillStyle = team.primary_color;
    ctx.fillRect(0, 0, s, s * 0.14);
    ctx.fillStyle = "#141C31";
    for (let r = 0; r < 3; r += 1) ctx.fillRect(s * 0.06, s * (0.2 + r * 0.12), s * 0.88, s * 0.09);
    ctx.fillStyle = team.secondary_color;
    ctx.font = FONT(s * 0.07);
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(team.short_name, s * 0.06, s * 0.07);
    ctx.fillStyle = "#FF7043";
    for (let b = 0; b < 6; b += 1) {
      ctx.beginPath();
      ctx.arc(s * (0.62 + b * 0.055), s * 0.07, s * 0.018, 0, Math.PI * 2);
      b < 4 ? ctx.fill() : ctx.stroke();
    }
  },
  split(ctx, s, team) {
    ctx.fillStyle = team.primary_color;
    ctx.fillRect(0, 0, s / 2, s);
    ctx.fillStyle = "#0B1020";
    ctx.fillRect(s / 2, 0, s / 2, s);
    ctx.fillStyle = team.secondary_color;
    ctx.fillRect(s / 2 - 3, 0, 6, s);
  },
  floodlights(ctx, s) {
    const sky = ctx.createLinearGradient(0, 0, 0, s);
    sky.addColorStop(0, "#060914");
    sky.addColorStop(1, "#13301f");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, s, s);
    [[0.15, 0.12], [0.85, 0.12], [0.38, 0.2], [0.62, 0.2]].forEach(([fx, fy]) => {
      const glow = ctx.createRadialGradient(s * fx, s * fy, 0, s * fx, s * fy, s * 0.28);
      glow.addColorStop(0, "rgba(255,246,216,0.85)");
      glow.addColorStop(1, "rgba(255,246,216,0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, s, s);
    });
    ctx.fillStyle = "#2f6b3c";
    ctx.beginPath();
    ctx.ellipse(s / 2, s * 1.05, s * 0.75, s * 0.35, 0, 0, Math.PI * 2);
    ctx.fill();
  },
  rain(ctx, s) {
    ctx.fillStyle = "#1a2236";
    ctx.fillRect(0, 0, s, s);
    ctx.strokeStyle = "rgba(154,166,194,0.35)";
    ctx.lineWidth = 2;
    for (let i = 0; i < 90; i += 1) {
      const x = (i * 97) % s;
      const y = (i * 53) % s;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x - 8, y + 26);
      ctx.stroke();
    }
    ctx.fillStyle = "#9aa6c2";
    ctx.fillRect(s * 0.1, s * 0.62, s * 0.8, s * 0.04); // the covers
  },
  review(ctx, s, team) {
    ctx.fillStyle = "#0B1020";
    ctx.fillRect(0, 0, s, s);
    ctx.strokeStyle = team.secondary_color;
    ctx.lineWidth = 3;
    ctx.strokeRect(s * 0.06, s * 0.36, s * 0.88, s * 0.5);
    ctx.strokeStyle = "rgba(200,255,77,0.25)";
    for (let i = 1; i < 4; i += 1) {
      ctx.beginPath();
      ctx.moveTo(s * (0.06 + i * 0.22), s * 0.36);
      ctx.lineTo(s * (0.06 + i * 0.22), s * 0.86);
      ctx.stroke();
    }
  },
};

/**
 * Draw a meme. `template` is {layout_config} from the API (or null for the default).
 * Returns nothing; the canvas then holds the image (use canvas.toBlob to download).
 */
export function renderMeme(canvas, { template, caption, team, size = 1080 }) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  canvas.width = size;
  canvas.height = size;
  const t = { ...DEFAULT_TEAM, ...(team || {}) };
  const layout = template?.layout_config ?? { background: "scoreboard", text: "bottom" };
  (BACKGROUNDS[layout.background] ?? BACKGROUNDS.scoreboard)(ctx, size, t);
  const text = caption?.trim() || " ";
  const pad = size * 0.06;
  const box = { x: size / 2, width: size - pad * 2, startPx: size * 0.1 };

  if (layout.text === "split") {
    const [left, right] = layout.labels ?? ["Before", "After"];
    ctx.font = FONT(size * 0.045);
    ctx.fillStyle = "#F5F7FA";
    ctx.textAlign = "center";
    ctx.fillText(left.toUpperCase(), size * 0.25, size * 0.08);
    ctx.fillText(right.toUpperCase(), size * 0.75, size * 0.08);
    drawCaption(ctx, { ...box, text, y: size * 0.6, height: size * 0.34 });
  } else if (layout.text === "top") {
    drawCaption(ctx, { ...box, text, y: pad, height: size * 0.28 });
    if (layout.stamp) {
      ctx.save();
      ctx.translate(size / 2, size * 0.61);
      ctx.rotate(-0.08);
      ctx.font = FONT(size * 0.07);
      ctx.fillStyle = "#FF7043";
      ctx.textAlign = "center";
      ctx.fillText(layout.stamp, 0, 0);
      ctx.restore();
    }
  } else if (layout.text === "center") {
    drawCaption(ctx, { ...box, text, y: size * 0.3, height: size * 0.4, color: "#C8FF4D" });
  } else {
    drawCaption(ctx, { ...box, text, y: size * 0.6, height: size * 0.34 });
  }

  ctx.font = `600 ${Math.round(size * 0.022)}px "Inter", sans-serif`;
  ctx.textAlign = "right";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "rgba(245,247,250,0.6)";
  ctx.fillText("NPL ADDA · fan-made", size - pad, size - pad / 2);
}

export async function ensureMemeFonts() {
  try {
    await Promise.all([
      document.fonts?.load('800 64px "Barlow Condensed"'),
      document.fonts?.load('700 64px "Noto Sans Devanagari"'),
    ]);
  } catch {
    /* fall back to system fonts */
  }
}
