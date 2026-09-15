// J.A.R.V.I.S. ambient particle field -- lightweight canvas HUD backdrop.
// Convention: this runs once, mounted behind all UI (#jarvis-particles,
// z-index: 0 in jarvis-fx.css). Any future full-screen panel (R&D
// workspace, CAD viewer) should keep this canvas visible behind it for a
// consistent "alive" background, unless the panel needs full focus (in
// which case fade its opacity down rather than removing it).

(function () {
  const canvas = document.getElementById('jarvis-particles');
  if (!canvas) return;

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduceMotion) return;

  const ctx = canvas.getContext('2d');
  let width = 0;
  let height = 0;
  let dpr = Math.min(window.devicePixelRatio || 1, 2);

  const PARTICLE_COUNT = 70;
  const LINK_DISTANCE = 130;
  const MOUSE_INFLUENCE = 160;

  let particles = [];
  let mouse = { x: -9999, y: -9999 };

  // Speaking state (0 -> 1, eased) drives extra jitter/glow so the field
  // visibly reacts while JARVIS talks -- set via window.jarvisParticles,
  // called from renderer.js for both the in-app text/mic flow and the
  // real wake-word voice loop (pushed from the backend over IPC).
  let speaking = false;
  let speakEnergy = 0;

  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function makeParticle() {
    return {
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.25,
      vy: (Math.random() - 0.5) * 0.25,
      r: Math.random() * 1.4 + 0.6,
    };
  }

  function init() {
    resize();
    particles = Array.from({ length: PARTICLE_COUNT }, makeParticle);
  }

  function step() {
    // Ease toward the target each frame instead of snapping, so speech
    // starting/stopping ramps the field up/down rather than jump-cutting.
    speakEnergy += ((speaking ? 1 : 0) - speakEnergy) * 0.08;

    ctx.clearRect(0, 0, width, height);

    for (const p of particles) {
      // Gentle drift toward cursor within influence radius -- the "HUD
      // reacting to your presence" feel, without being distracting.
      const dx = mouse.x - p.x;
      const dy = mouse.y - p.y;
      const dist = Math.hypot(dx, dy);
      if (dist < MOUSE_INFLUENCE) {
        const pull = (1 - dist / MOUSE_INFLUENCE) * 0.02;
        p.vx += dx * pull * 0.01;
        p.vy += dy * pull * 0.01;
      }

      // Speaking jitter -- small random kicks so the field visibly
      // agitates while JARVIS talks, on top of whatever drift is already
      // happening. Scaled by speakEnergy so it fades in/out smoothly.
      if (speakEnergy > 0.01) {
        p.vx += (Math.random() - 0.5) * 0.12 * speakEnergy;
        p.vy += (Math.random() - 0.5) * 0.12 * speakEnergy;
      }

      p.x += p.vx;
      p.y += p.vy;
      p.vx *= 0.99;
      p.vy *= 0.99;

      if (p.x < 0 || p.x > width) p.vx *= -1;
      if (p.y < 0 || p.y > height) p.vy *= -1;
      p.x = Math.max(0, Math.min(width, p.x));
      p.y = Math.max(0, Math.min(height, p.y));
    }

    // Connective lines between nearby particles -- the "circuit trace" look.
    // Reach and brightness both pulse up while speaking.
    const linkDistance = LINK_DISTANCE * (1 + speakEnergy * 0.25);
    ctx.lineWidth = 1;
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i];
        const b = particles[j];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (dist < linkDistance) {
          const alpha = (1 - dist / linkDistance) * (0.35 + speakEnergy * 0.25);
          ctx.strokeStyle = `rgba(226, 28, 28, ${alpha})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    // Particle nodes -- brighter and slightly larger while speaking.
    for (const p of particles) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * (1 + speakEnergy * 0.4), 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255, 46, 46, ${0.55 + speakEnergy * 0.35})`;
      ctx.shadowColor = 'rgba(226, 28, 28, 0.6)';
      ctx.shadowBlur = 6 + speakEnergy * 10;
      ctx.fill();
    }
    ctx.shadowBlur = 0;

    requestAnimationFrame(step);
  }

  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  });
  window.addEventListener('mouseleave', () => {
    mouse.x = -9999;
    mouse.y = -9999;
  });

  init();
  requestAnimationFrame(step);

  window.jarvisParticles = {
    setSpeaking(active) {
      speaking = !!active;
    },
  };
})();
