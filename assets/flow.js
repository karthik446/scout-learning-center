'use strict';
// Prototype B: explicit playback, returning synchronous replies, queue residency.
(() => {
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  document.querySelectorAll('.flow').forEach(host => {
    const steps = [...host.querySelectorAll('.flow-calls li')];
    const paths = [...host.querySelectorAll('.flow-edge')];
    const nodes = [...host.querySelectorAll('.flow-node')];
    const packet = host.querySelector('.flow-packet');
    const token = host.querySelector('.flow-queued');
    const caption = host.querySelector('.flow-caption');
    const button = action => host.querySelector(`[data-action="${action}"]`);
    const play = button('play');
    let index = 0, animation = null, playing = false, phase = 'call', queued = null;
    const path = () => paths[Number(steps[index].dataset.edge)];
    function pause() {
      playing = false;
      if (animation) animation.pause();
      play.textContent = 'Play';
    }
    function render() {
      const edge = path();
      paths.forEach(p => p.classList.toggle('active', p === edge));
      steps.forEach((s, i) => s.classList.toggle('active', i === index));
      nodes.forEach(n => n.classList.toggle('active', [edge.dataset.from, edge.dataset.to].includes(n.dataset.node)));
      caption.textContent = `${index + 1} / ${steps.length} — ${steps[index].dataset.caption}`;
      button('previous').disabled = index === 0;
      button('next').disabled = index === steps.length - 1;
      host.dataset.step = String(index);
    }
    function select(i) {
      pause();
      if (animation) animation.cancel();
      animation = null;
      packet.classList.add('hidden');
      token.classList.add('hidden');
      queued = null;
      index = i;
      phase = 'call';
      render();
    }
    function advance() {
      if (!playing) return;
      if (animation) animation.cancel();
      animation = null;
      if (index === steps.length - 1) {
        pause();
        packet.classList.add('hidden');
        play.textContent = 'Replay';
        return;
      }
      index++;
      render();
      move();
    }
    function move(reverse = false) {
      if (animation) animation.cancel();
      phase = reverse ? 'reply' : 'call';
      const edge = path();
      if (queued === edge.dataset.from) {
        queued = null;
        token.classList.add('hidden');
      }
      packet.classList.remove('hidden');
      packet.classList.toggle('reply', reverse || edge.dataset.kind === 'reply');
      const length = edge.getTotalLength();
      const frames = Array.from({length: 81}, (_, i) => {
        const point = edge.getPointAtLength(length * (reverse ? 1 - i / 80 : i / 80));
        return {transform: `translate(${point.x}px, ${point.y}px)`};
      });
      animation = packet.animate(frames, {duration: 1600, fill: 'forwards', easing: 'linear'});
      animation.onfinish = () => {
        if (!playing) return;
        if (!reverse && edge.dataset.kind === 'sync') {
          caption.textContent += ' Reply returns to this caller (schematic, not a latency scale).';
          move(true);
          return;
        }
        const destination = nodes.find(n => n.dataset.node === edge.dataset.to);
        if (edge.dataset.kind === 'async' && destination.dataset.kind === 'queue') {
          const box = destination.getBBox();
          token.setAttribute('cx', box.x + box.width - 14);
          token.setAttribute('cy', box.y + box.height - 14);
          queued = edge.dataset.to;
          packet.classList.add('hidden');
          token.classList.remove('hidden');
          phase = 'waiting';
          caption.textContent += ' Event parked in the queue until the worker takes it.';
          animation.cancel();
          animation = token.animate([{opacity: 1}, {opacity: 1}], {duration: 1800});
          animation.onfinish = advance;
        } else advance();
      };
    }
    play.addEventListener('click', () => {
      if (motion.matches) return;
      if (playing) { pause(); return; }
      if (index === steps.length - 1 && !animation) select(0);
      playing = true;
      play.textContent = 'Pause';
      if (animation && animation.playState === 'paused') animation.play();
      else move(phase === 'reply');
    });
    button('previous').addEventListener('click', () => select(Math.max(0, index - 1)));
    button('next').addEventListener('click', () => select(Math.min(steps.length - 1, index + 1)));
    button('reset').addEventListener('click', () => select(0));
    function preference() {
      select(index);
      play.disabled = motion.matches;
      host.dataset.reducedMotion = String(motion.matches);
      host.querySelector('.flow-mode').textContent = motion.matches
        ? 'Reduced motion: manual step-through, no movement.'
        : 'Motion starts only when you choose Play. Pause holds the current position.';
    }
    motion.addEventListener('change', preference);
    preference();
  });
})();
