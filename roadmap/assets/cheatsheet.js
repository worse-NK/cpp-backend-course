(function () {
    'use strict';
    const groups = Array.from(document.querySelectorAll('.reference-group'));
    const input = document.getElementById('reference-search');
    const status = document.getElementById('search-status');
    const normalize = value => value.toLocaleLowerCase('ru').replace(/ё/g, 'е');
    const records = groups.map(group => ({
        group, title: normalize(group.querySelector('h2').textContent),
        sections: Array.from(group.querySelectorAll('.reference-section')).map(section => ({
            section, title: normalize(section.querySelector('h3').textContent),
            items: Array.from(section.querySelectorAll('.reference-item')).map(item => ({ item, text: normalize(item.textContent) }))
        }))
    }));
    let savedOpen = null;
    function filter() {
        const query = normalize(input.value.trim());
        if (query && savedOpen === null) savedOpen = groups.map(group => group.open);
        let count = 0, visibleGroups = 0;
        records.forEach(record => {
            let groupCount = 0;
            record.sections.forEach(part => {
                const matchHeading = record.title.includes(query) || part.title.includes(query);
                let sectionCount = 0;
                part.items.forEach(entry => {
                    entry.item.hidden = !!query && !matchHeading && !entry.text.includes(query);
                    if (!entry.item.hidden) sectionCount++;
                });
                part.section.hidden = !sectionCount;
                groupCount += sectionCount;
            });
            record.group.hidden = !groupCount;
            record.group.querySelector('.section-toc').hidden = !!query;
            record.group.querySelector('.chapter-pagination').hidden = !!query;
            if (query && groupCount) record.group.open = true;
            if (groupCount) visibleGroups++;
            count += groupCount;
        });
        if (!query && savedOpen !== null) { groups.forEach((group, i) => { group.open = savedOpen[i]; }); savedOpen = null; }
        status.textContent = query ? (count ? 'Найдено карточек: ' + count + ' · разделов: ' + visibleGroups : 'Ничего не найдено. Попробуй другое слово или очисти поиск.') : '';
    }
    function followHash() {
        let id;
        try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { return; }
        const target = document.getElementById(id);
        if (!target) return;
        if (input.value) { input.value = ''; filter(); }
        const group = target.closest('.reference-group');
        if (group) group.open = true;
        document.querySelectorAll('aside nav a').forEach(link => {
            if (group && link.hash === '#' + group.id) link.setAttribute('aria-current', 'location');
            else link.removeAttribute('aria-current');
        });
        target.scrollIntoView({ block: 'start' });
        const focusTarget = target.matches('.reference-group') ? target.querySelector('summary') : target;
        if (focusTarget.tabIndex >= -1) focusTarget.focus({ preventScroll: true });
    }
    document.querySelector('.search-panel').hidden = false;
    input.addEventListener('input', filter);
    document.getElementById('clear-search').addEventListener('click', () => { input.value = ''; filter(); input.focus(); });
    document.getElementById('expand-all').addEventListener('click', () => groups.forEach(group => { group.open = true; }));
    document.getElementById('collapse-all').addEventListener('click', () => groups.forEach(group => { group.open = false; }));
    document.addEventListener('click', event => {
        const link = event.target.closest('a[href^="#"]');
        if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
        // The same hash does not dispatch hashchange; it must still reopen a closed section.
        if (link.hash === location.hash) { event.preventDefault(); followHash(); }
    });
    window.addEventListener('hashchange', followHash);
    const contents = document.querySelector('.contents-disclosure');
    if (window.matchMedia('(max-width: 860px)').matches) contents.open = false;
    document.querySelectorAll('a[href="#contents"]').forEach(link => link.addEventListener('click', () => { contents.open = true; }));
    let printOpen;
    window.addEventListener('beforeprint', () => { printOpen = groups.map(group => group.open); groups.forEach(group => { group.open = true; }); });
    window.addEventListener('afterprint', () => { if (printOpen) groups.forEach((group, i) => { group.open = printOpen[i]; }); });
    if (location.hash) followHash();
}());
