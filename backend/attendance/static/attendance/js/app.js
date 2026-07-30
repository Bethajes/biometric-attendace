document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-table-search]');
    if (!trigger) return;
    const input = document.querySelector(trigger.dataset.tableSearch);
    if (input) input.focus();
});

// Dark mode toggle
(function() {
    var toggle = document.getElementById('theme-toggle');
    var icon = document.getElementById('theme-icon');
    var html = document.documentElement;

    var saved = localStorage.getItem('theme');
    if (saved) {
        html.setAttribute('data-theme', saved);
        if (icon) icon.innerHTML = saved === 'dark' ? '\u2600' : '\u263E';
    }

    if (toggle) {
        toggle.addEventListener('click', function() {
            var current = html.getAttribute('data-theme');
            var next = current === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            if (icon) icon.innerHTML = next === 'dark' ? '\u2600' : '\u263E';
        });
    }
})();
