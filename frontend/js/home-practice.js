(() => {
  const screen = document.querySelector('#practicePreview .preview-screen');
  const detail = screen.querySelector('[data-preview-detail]');
  const question = screen.querySelector('[data-preview-question]');
  const options = [...detail.querySelectorAll('.practice-option')];
  const submit = detail.querySelector('[data-preview-submit]');
  const master = detail.querySelector('[data-preview-master]');
  const feedback = detail.querySelector('[data-preview-feedback]');
  const chips = [...screen.querySelectorAll('[data-preview-status]')];
  const pointer = screen.querySelector('.preview-pointer');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let motion, timers = [], complete = false, visible = false;

  function answer(index, graded = false) {
    for (const [optionIndex, option] of options.entries()) {
      option.classList.toggle('is-chosen', index === optionIndex);
      option.classList.toggle('is-correct', graded && optionIndex === 1);
      option.classList.toggle('is-wrong', graded && index !== 1 && optionIndex === index);
    }
    submit.disabled = index === null;
    submit.textContent = graded ? '重新作答' : '提交答案';
    feedback.textContent = !graded ? '' : index === 1
      ? '回答正确。每次把候选区间缩小一半，最坏情况需要 O(log n) 次比较。'
      : '回答错误。O(n) 是顺序查找的最坏复杂度，再试一次。';
  }

  function setMastered(mastered) {
    for (const chip of chips) {
      chip.classList.toggle('chip-mastered', mastered);
      chip.classList.toggle('chip-pending', !mastered);
      chip.textContent = mastered ? '已掌握' : '待刷';
    }
    master.classList.toggle('is-recorded', mastered);
  }

  function stop() {
    motion?.cancel();
    motion = undefined;
    timers.forEach(timer => clearTimeout(timer));
    timers = [];
    pointer.hidden = true;
  }

  function finish(state) {
    complete = true;
    stop();
    question.classList.add('is-active');
    answer(1, true);
    setMastered(true);
    screen.dataset.playback = state;
    observer?.disconnect();
  }

  function play() {
    const steps = [
      [question, .11, () => question.classList.add('is-active')],
      [options[2], .24, () => answer(2)],
      [submit, .36, () => answer(2, true)],
      [submit, .55, () => answer(null)],
      [options[1], .67, () => answer(1)],
      [submit, .79, () => answer(1, true)],
      [master, .92, () => setMastered(true)]
    ];
    const origin = screen.getBoundingClientRect();
    const point = target => {
      const rect = target.getBoundingClientRect();
      const x = target === submit ? rect.width / 2 : Math.min(rect.width / 2, 64);
      return [rect.left - origin.left - screen.clientLeft + x - 4,
        rect.top - origin.top - screen.clientTop + rect.height / 2 - 2];
    };
    const key = ([x, y], offset, opacity = 1, scale = 1) => ({
      offset, opacity, easing: 'ease-in-out',
      transform: `translate(${x}px,${y}px) scale(${scale})`
    });
    const [x, y] = point(question);
    const keyframes = [key([x + 34, y - 22], 0, 0)];
    for (const [target, offset] of steps) {
      const position = point(target);
      keyframes.push(key(position, offset - .02), key(position, offset, 1, .72), key(position, offset + .025));
    }
    keyframes.push(key(point(master), 1, 0));
    const duration = 5000;
    question.classList.remove('is-active');
    screen.dataset.playback = 'playing';
    pointer.hidden = false;
    const playback = pointer.animate(keyframes, {duration, fill: 'both'});
    motion = playback;
    timers = steps.map(([, offset, action]) => setTimeout(action, duration * offset));
    playback.onfinish = () => {
      if (motion === playback) finish('complete');
    };
  }

  function sync() {
    if (complete) return;
    if (!observer || reduced.matches) {
      finish('static');
    } else if (!visible || document.hidden) {
      if (!motion) return;
      stop();
      question.classList.add('is-active');
      answer(null);
      setMastered(false);
      screen.dataset.playback = 'waiting';
    } else if (!motion) {
      play();
    }
  }

  const observer = 'IntersectionObserver' in window && pointer.animate ? new IntersectionObserver(([entry]) => {
    const viewportHeight = entry.rootBounds?.height ?? innerHeight;
    const threshold = viewportHeight < entry.boundingClientRect.height ? .4 : .65;
    visible = entry.intersectionRatio >= threshold;
    sync();
  }, {threshold: [.4, .65]}) : null;
  screen.dataset.playback = 'waiting';
  observer?.observe(detail);
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', sync);
  sync();
})();
