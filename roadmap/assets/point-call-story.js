// Station 0: keep the two Points on screen while ordinary document scrolling
// selects a snapshot. The ordered list is the complete, independent text version.
(() => {
  'use strict';
  if (!window.customElements || customElements.get('point-call-story')) return;

  const picture = document.createElement('template');
  picture.innerHTML = `
    <div class="pcs-stage" aria-hidden="true" data-no-terms="">
      <div class="pcs-stage-head"><span class="pcs-context"></span><span class="pcs-index"></span></div>
      <code class="pcs-line" translate="no"></code>
      <div class="pcs-method"><code class="pcs-assignment" translate="no">this-&gt;x = value;</code><span class="pcs-arg"></span></div>
      <div class="pcs-link">
        <span class="pcs-this-label"></span>
        <svg class="pcs-arrows" viewBox="0 0 360 40" preserveAspectRatio="none" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2">
          <path class="pcs-to-a" visibility="hidden" vector-effect="non-scaling-stroke" d="M180 1 V7 Q180 15 172 15 H98 Q90 15 90 23 V36 M85 30 L90 36 L95 30"/>
          <path class="pcs-to-b" visibility="hidden" vector-effect="non-scaling-stroke" d="M180 1 V7 Q180 15 188 15 H262 Q270 15 270 23 V36 M265 30 L270 36 L275 30"/>
        </svg>
      </div>
      <div class="pcs-objects">
        <div class="pcs-object" data-object="a"><span class="pcs-name" translate="no">Point a</span><span class="pcs-field"><span>x</span><strong class="pcs-value"></strong></span></div>
        <div class="pcs-object" data-object="b"><span class="pcs-name" translate="no">Point b</span><span class="pcs-field"><span>x</span><strong class="pcs-value"></strong></span></div>
      </div>
      <div class="pcs-stage-foot"></div>
    </div>`;

  function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
  }

  class PointCallStory extends HTMLElement {
    connectedCallback() {
      // During parsing the element may be connected before its subtree exists.
      queueMicrotask(() => {
        if (this.isConnected && !this._detach) this.mountStory();
      });
    }

    disconnectedCallback() {
      if (this._detach) this._detach();
    }

    mountStory() {
      const track = this.querySelector('.pcs-track');
      const items = track ? Array.from(track.querySelectorAll('.pcs-beats > li')) : [];
      if (!items.length) return;
      const stage = picture.content.firstElementChild.cloneNode(true);
      const get = selector => stage.querySelector(selector);
      const context = get('.pcs-context'), page = get('.pcs-index'), line = get('.pcs-line');
      const detail = get('.pcs-assignment'), arg = get('.pcs-arg');
      const label = get('.pcs-this-label'), foot = get('.pcs-stage-foot');
      const points = ['a', 'b'].map(name => ({
        name, value: get('[data-object="' + name + '"] .pcs-value'), arrow: get('.pcs-to-' + name)
      }));
      const beats = track.querySelector('.pcs-beats');
      const skip = this.querySelector('.pcs-skip'), after = this.querySelector('.pcs-after');
      track.prepend(stage);
      this.classList.add('pcs-enhanced');
      let current = -1, raf = 0;

      const show = index => {
        if (index === current) return;
        if (current >= 0) items[current].removeAttribute('aria-current');
        current = index;
        const item = items[index], frame = item.dataset;
        const inMethod = frame.target === 'a' || frame.target === 'b';
        item.setAttribute('aria-current', 'step');
        this.dataset.step = String(index);
        this.dataset.target = frame.target;
        this.dataset.phase = frame.phase;
        setText(context, inMethod ? 'Вызов из main' : 'В main');
        setText(page, (index + 1) + ' / ' + items.length);
        setText(line, frame.line);
        setText(detail, inMethod ? 'this->x = value;' : frame.phase === 'ready' ? 'int x = 0;' : 'return x;');
        setText(arg, inMethod ? 'value: ' + frame.arg : frame.phase === 'ready' ? 'при создании' : 'чтение в getX');
        setText(label, inMethod ? 'this' : 'Вне setX');
        points.forEach(p => {
          setText(p.value, frame[p.name]);
          p.arrow.setAttribute('visibility', p.name === frame.target ? 'visible' : 'hidden');
        });
        let note;
        if (frame.phase === 'ready') note = 'У каждой точки своё поле x.';
        else if (frame.phase === 'enter') note = 'Выбрана точка ' + frame.target + '. Её поле ещё не изменилось.';
        else if (frame.phase === 'write') note = 'Записали ' + frame.arg + ' в поле x точки ' + frame.target + '.';
        else note = 'Вывод программы: ' + frame.a + ' ' + frame.b;
        setText(foot, note);
      };
      const measure = () => {
        raf = 0;
        const h = window.innerHeight;
        const box = stage.getBoundingClientRect(), column = beats.getBoundingClientRect();
        const css = getComputedStyle(stage);
        const inset = Math.max(0, parseFloat(css.top) || 0);
        const stacked = column.left < box.right - 1;
        const lineY = css.position !== 'sticky' ? h * .48 : stacked
          ? Math.min(h * .9, inset + box.height + Math.max(0, h - inset - box.height) * .43)
          : Math.min(h * .8, inset + box.height * .5);
        let index = 0;
        for (let i = 1; i < items.length; i++) {
          const rect = items[i].getBoundingClientRect();
          if (rect.top + rect.height * .32 > lineY) break;
          index = i;
        }
        show(index);
      };
      const schedule = () => {
        if (!raf) raf = requestAnimationFrame(measure);
      };
      const jump = () => {
        after.focus({preventScroll: true});
        after.scrollIntoView({block: 'start', behavior: 'instant'});
      };
      window.addEventListener('scroll', schedule, {passive: true});
      window.addEventListener('resize', schedule);
      const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(schedule) : null;
      if (observer) { observer.observe(track); observer.observe(stage); }
      if (skip && after) skip.addEventListener('click', jump);
      show(0);
      schedule();
      this._detach = () => {
        window.removeEventListener('scroll', schedule);
        window.removeEventListener('resize', schedule);
        if (observer) observer.disconnect();
        if (skip && after) skip.removeEventListener('click', jump);
        cancelAnimationFrame(raf);
        if (current >= 0) items[current].removeAttribute('aria-current');
        stage.remove();
        this.classList.remove('pcs-enhanced');
        delete this.dataset.step; delete this.dataset.target; delete this.dataset.phase;
        this._detach = null;
      };
    }
  }
  customElements.define('point-call-story', PointCallStory);
})();
