(() => {
  const content = document.getElementById('demoContent');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const canObserve = 'IntersectionObserver' in window;
  const shortViewportThreshold = .4, startThreshold = .88;
  let inView = false, played = false, frame = 0, restoreText;

  function stop() {
    cancelAnimationFrame(frame);
    frame = 0;
    restoreText?.();
    restoreText = undefined;
    delete content.dataset.demoStage;
  }

  function play() {
    if (content.dataset.demoStage !== 'waiting') content.dataset.demoStage = 'waiting';
    const message = content.querySelector('.demo-question-text');
    const question = Array.from(message.textContent);
    const draft = content.querySelector('.demo-draft');
    const response = content.querySelector('.demo-response');
    const walker = document.createTreeWalker(response, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    const segments = nodes.map(node => {
      const letters = Array.from(node.data);
      const rest = document.createElement('span');
      rest.className = 'demo-stream-rest';
      rest.setAttribute('aria-hidden', 'true');
      rest.textContent = node.data;
      node.after(rest);
      node.data = '';
      return {node, letters, rest};
    });
    const answerLength = segments.reduce((total, {letters}) => total + letters.length, 0);
    let slide;
    restoreText = () => {
      slide?.cancel();
      for (const {node, letters, rest} of segments) {
        node.data = letters.join('');
        rest.remove();
      }
      draft.textContent = '';
    };

    const clickAt = 360, typingAt = 560, sendAt = 1830, arriveAt = 2330, answerAt = 2810, completeAt = 4870;
    let start, shown = -1;
    function step(now) {
      start ??= now;
      const elapsed = now - start;
      if (elapsed >= completeAt) {
        played = true;
        stop();
        content.querySelector('.demo-source').animate([{opacity: 0}, {opacity: 1}], {duration: 180});
        return;
      }
      const stage = elapsed < clickAt ? 'aiming'
        : elapsed < typingAt ? 'clicking'
        : elapsed < sendAt ? 'typing'
        : elapsed < arriveAt ? 'sending'
        : elapsed < answerAt ? 'thinking' : 'answering';
      if (content.dataset.demoStage !== stage) {
        const from = stage === 'sending' ? draft.getBoundingClientRect() : null;
        content.dataset.demoStage = stage;
        if (from?.height) {
          const to = message.getBoundingClientRect();
          const scale = parseFloat(getComputedStyle(draft).fontSize) / parseFloat(getComputedStyle(message).fontSize);
          slide = message.animate([
            {transform: `translate(${from.left - to.left}px,${from.top - to.top}px) scale(${scale})`},
            {transform: 'translate(0,0) scale(1)'}
          ], {duration: arriveAt - elapsed, easing: 'cubic-bezier(.22,.68,.18,1)', fill: 'both'});
        } else {
          slide?.cancel();
          slide = undefined;
        }
      }
      if (stage === 'typing') {
        const count = Math.ceil(question.length * (elapsed - typingAt) / (sendAt - typingAt));
        if (count !== shown) draft.textContent = question.slice(0, count).join('');
        shown = count;
      }
      if (stage === 'answering') {
        let count = Math.ceil(answerLength * (elapsed - answerAt) / (completeAt - answerAt));
        for (const {node, letters, rest} of segments) {
          const visible = letters.slice(0, Math.max(0, count)).join('');
          if (node.data !== visible) {
            node.data = visible;
            rest.textContent = letters.slice(Math.max(0, count)).join('');
          }
          count -= letters.length;
        }
      }
      frame = requestAnimationFrame(step);
    }
    frame = requestAnimationFrame(step);
  }

  function sync() {
    if (!canObserve || reduced.matches) {
      stop();
      return;
    }
    if (played) return;
    if (!inView || document.hidden) {
      if (frame) stop();
      if (content.dataset.demoStage !== 'waiting') content.dataset.demoStage = 'waiting';
    } else if (!frame) {
      play();
    }
  }

  if (canObserve) {
    new IntersectionObserver(([entry]) => {
      const viewportHeight = entry.rootBounds?.height ?? innerHeight;
      const threshold = viewportHeight < entry.boundingClientRect.height ? shortViewportThreshold : startThreshold;
      inView = entry.intersectionRatio >= threshold;
      sync();
    }, {threshold: [shortViewportThreshold, startThreshold]}).observe(content);
  }
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', sync);
  sync();

})();
