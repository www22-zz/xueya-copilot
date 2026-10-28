/* Shared in-page selects keep options and the custom pointer in the same UI. */
(() => {
  document.addEventListener('DOMContentLoaded', () => {
    let active = null, sequence = 0;
    const enhanced = new WeakSet();
    function close() {
      if (!active) return;
      active.trigger.setAttribute('aria-expanded', 'false');
      active.trigger.removeAttribute('aria-activedescendant');
      active.menu.remove();
      active = null;
    }
    function enhance(select) {
      if (enhanced.has(select) || select.multiple || select.size > 1) return;
      enhanced.add(select);
      const wrapper = document.createElement('span');
      wrapper.className = 'practice-select'+(select.classList.contains('form-field')?' form-field':'');
      const trigger = document.createElement('button');
      trigger.type = 'button';
      trigger.className = 'practice-select-trigger';
      trigger.setAttribute('role', 'combobox');
      trigger.setAttribute('aria-haspopup', 'listbox');
      trigger.setAttribute('aria-expanded', 'false');
      const label = select.getAttribute('aria-label') || select.labels?.[0]?.textContent.replace(select.textContent,'').trim() || '选择';
      trigger.setAttribute('aria-label', label);
      const menuId = `practice-select-${++sequence}`;
      trigger.setAttribute('aria-controls', menuId);
      select.before(wrapper);
      wrapper.append(select, trigger);
      select.hidden = true;
      select.tabIndex = -1;
      select.setAttribute('aria-hidden', 'true');
      function replacement() {
        if (select.isConnected) return select;
        // Views can synchronously replace their toolbar after a change.
        if (select.id) return document.getElementById(select.id);
        for (const attribute of ['data-filter','data-analysis-filter']) {
          if (select.hasAttribute(attribute)) return document.querySelector(`select[${attribute}="${CSS.escape(select.getAttribute(attribute))}"]`);
        }
        return null;
      }
      function sync() {
        trigger.textContent = select.selectedOptions[0]?.textContent || label;
        trigger.disabled = select.disabled;
        if(select.validity.valid)trigger.removeAttribute('aria-invalid');
      }
      sync();
      select.addEventListener('change', sync);
      select.addEventListener('invalid', event => {
        event.preventDefault();trigger.setAttribute('aria-invalid','true');trigger.focus();
      });
      new MutationObserver(sync).observe(select,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['disabled','selected','label']});
      function open() {
        close();
        const menu = document.createElement('div');
        menu.id = menuId;
        menu.className = 'practice-select-menu';
        menu.setAttribute('role', 'listbox');
        menu.setAttribute('aria-label', label);
        // Keep focus on the combobox; modal focus management would otherwise
        // close and remove the option before its click can select a value.
        menu.addEventListener('pointerdown',event=>event.preventDefault());
        // Keep dialog/top-layer controls in their own layer when applicable.
        const topLayer=typeof menu.showPopover==='function';
        if(topLayer)menu.setAttribute('popover','manual');
        (select.closest('dialog') || document.body).append(menu);
        if(topLayer)menu.showPopover();
        // The newly opened list goes above older popovers, including the cursor.
        document.dispatchEvent(new Event('xueya:overlay-open'));
        const options = Array.from(select.options);
        let index = Math.max(0, select.selectedIndex);
        const items = options.map((option, i) => {
          const item = document.createElement('div');
          item.id = `${menuId}-${i}`;
          item.className = 'practice-select-option';
          item.setAttribute('role', 'option');
          item.setAttribute('aria-selected', String(option.selected));
          item.setAttribute('aria-disabled', String(option.disabled));
          item.textContent = option.textContent;
          item.hidden = option.hidden;
          item.addEventListener('pointermove', () => { if (!option.disabled) highlight(i); });
          item.addEventListener('click', () => choose(i));
          menu.append(item);
          return item;
        });
        function highlight(next) {
          if(items[next].classList.contains('is-active'))return;
          index = next;
          items.forEach((item, i) => item.classList.toggle('is-active', i === index));
          trigger.setAttribute('aria-activedescendant', items[index].id);
        }
        function reveal(next) {
          const item = items[next];
          if (item.offsetTop < menu.scrollTop) menu.scrollTop = item.offsetTop;
          else if (item.offsetTop + item.offsetHeight > menu.scrollTop + menu.clientHeight)
            menu.scrollTop = item.offsetTop + item.offsetHeight - menu.clientHeight;
        }
        function choose(next) {
          if (options[next].disabled || options[next].hidden) return;
          const changed = select.selectedIndex !== next;
          select.selectedIndex = next;
          sync();
          close();
          if (changed) select.dispatchEvent(new Event('change', {bubbles: true}));
          // Filtering can replace the entire toolbar synchronously.
          queueMicrotask(() => {
            const next = replacement();
            if(next){enhance(next);next.parentElement.querySelector('.practice-select-trigger')?.focus();}
          });
        }
        active = {select, trigger, menu, choose, step(direction) {
          let next = index;
          for (let n = 0; n < options.length; n++) {
            next = (next + direction + options.length) % options.length;
            if (!options[next].disabled && !options[next].hidden) { highlight(next); reveal(next); break; }
          }
        }, chooseActive() { choose(index); }, edge(last) {
          const candidates = options.map((o, i) => !o.disabled && !o.hidden ? i : -1).filter(i => i >= 0);
          if (candidates.length) { highlight(last ? candidates.at(-1) : candidates[0]); reveal(index); }
        }};
        trigger.setAttribute('aria-expanded', 'true');
        function position() {
          const rect = trigger.getBoundingClientRect();
          if (rect.bottom < 0 || rect.top > innerHeight) { close(); return; }
          menu.style.top = ''; menu.style.bottom = '';
          const width = Math.min(Math.max(rect.width, 180), innerWidth - 16);
          menu.style.width = `${width}px`;
          menu.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - width - 8))}px`;
          const below = innerHeight - rect.bottom - 12;
          const above = rect.top - 12;
          menu.style.maxHeight = `${Math.min(280, Math.max(below, above))}px`;
          if (below >= Math.min(280, menu.scrollHeight) || below >= above) menu.style.top = `${rect.bottom + 6}px`;
          else menu.style.bottom = `${innerHeight - rect.top + 6}px`;
        }
        active.position = position;
        position();
        if (items.length) { highlight(index); reveal(index); }
      }
      trigger.addEventListener('click', () => { if (active?.trigger === trigger) close(); else open(); });
      trigger.addEventListener('keydown', event => {
        if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' ', 'Escape'].includes(event.key)) {
          event.preventDefault();
          if (event.key === 'Escape') { close(); return; }
          if (active?.trigger !== trigger) { open(); return; }
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') active.step(event.key === 'ArrowDown' ? 1 : -1);
          else if (event.key === 'Home' || event.key === 'End') active.edge(event.key === 'End');
          else active.chooseActive();
        } else if (event.key === 'Tab') close();
      });
    }
    function scan() {
      if (active && !active.select.isConnected) close();
      // The course picker already has its own in-page menu.
      document.querySelectorAll('select:not(#courseSelect):not([hidden]):not([data-native-select])').forEach(enhance);
    }
    new MutationObserver(records=>{
      if(records.some(record=>[...record.addedNodes,...record.removedNodes].some(node=>node instanceof Element)))scan();
    }).observe(document.body, {childList: true, subtree: true});
    document.addEventListener('pointerdown', event => {
      if (active && !active.menu.contains(event.target) && !active.trigger.contains(event.target)) close();
    });
    document.addEventListener('focusin', event => { if (active && event.target !== active.trigger && !active.menu.contains(event.target)) close(); });
    document.addEventListener('keydown', event => {
      if(active&&event.key==='Escape'){event.preventDefault();event.stopPropagation();close();}
    },true);
    document.addEventListener('close',event=>{if(active&&event.target.contains(active.trigger))close();},true);
    document.addEventListener('scroll', event => { if (active && !active.menu.contains(event.target)) active.position(); }, true);
    window.addEventListener('resize', close);
    window.addEventListener('blur', close);
    scan();
  });
})();
