import { forwardRef, useEffect, useRef } from "react";

import { ensureMemeFonts, renderMeme } from "../lib/memeRender.js";

/** Draws a meme into a canvas whenever the template, caption or team change. */
const MemeCanvas = forwardRef(function MemeCanvas({ template, caption, team, size = 1080, label }, ref) {
  const local = useRef(null);
  const canvasRef = ref ?? local;

  useEffect(() => {
    let cancelled = false;
    ensureMemeFonts().then(() => {
      if (!cancelled && canvasRef.current) renderMeme(canvasRef.current, { template, caption, team, size });
    });
    return () => {
      cancelled = true;
    };
  }, [canvasRef, template, caption, team, size]);

  return <canvas ref={canvasRef} className="meme-canvas" role="img" aria-label={label ?? caption} />;
});

export default MemeCanvas;
